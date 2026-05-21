#!/usr/bin/env python3
"""Voice trace validation gate.

Validates that voice-session traces are present in Langfuse with correct
service attribution. Designed for local/dev execution against local Langfuse.

Usage:
    uv run python scripts/validate_voice_traces.py
    uv run python scripts/validate_voice_traces.py --host http://localhost:3001
    uv run python scripts/validate_voice_traces.py --help
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path


# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments with env-var defaults."""
    parser = argparse.ArgumentParser(
        description="Voice trace validation gate for Langfuse",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("LANGFUSE_HOST", "http://localhost:3001"),
        help="Langfuse host URL (default: $LANGFUSE_HOST or http://localhost:3001)",
    )
    parser.add_argument(
        "--public-key",
        default=os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        help="Langfuse public key (default: $LANGFUSE_PUBLIC_KEY or pk-lf-dev)",
    )
    parser.add_argument(
        "--secret-key",
        default=os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        help="Langfuse secret key (default: $LANGFUSE_SECRET_KEY or sk-lf-dev)",
    )
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=5,
        help="How far back to look for traces (default: 5 minutes)",
    )
    parser.add_argument(
        "--skip-produce",
        action="store_true",
        help="Skip producing a new trace; only validate existing traces",
    )
    return parser.parse_args()


def check_langfuse_connectivity(host: str, public_key: str, secret_key: str) -> bool:
    """Verify Langfuse API is reachable and auth works."""
    from langfuse import Langfuse

    try:
        lf = Langfuse(
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )
        result = lf.auth_check()
        lf.flush()
        if not result:
            print("ERROR: Langfuse auth_check returned False")
            return False
        print(f"OK: Langfuse connectivity verified (host={host})")
        return True
    except Exception as e:
        print(f"ERROR: Langfuse connectivity failed: {e}")
        return False


def produce_voice_trace() -> str:
    """Produce a deterministic voice-session trace via update_voice_trace.

    Returns the expected session_id.
    """
    from src.voice.observability import update_voice_trace

    call_id = f"validate-{int(time.time())}"
    session_id = f"voice-{call_id}"

    update_voice_trace(
        call_id=call_id,
        status="completed",
        duration_sec=10,
        session_id=session_id,
    )
    print(f"OK: Produced voice-session trace (session_id={session_id})")
    return session_id


def wait_for_ingestion(seconds: int = 3) -> None:
    """Wait briefly for Langfuse to ingest the trace."""
    print(f"    Waiting {seconds}s for Langfuse ingestion...")
    time.sleep(seconds)


def validate_traces(lookback_minutes: int, expected_session_id: str | None = None) -> dict:
    """Read back voice-session traces from Langfuse and validate.

    Args:
        lookback_minutes: How far back to look for traces.
        expected_session_id: If provided, filter traces to match this session_id.
            When None (e.g., --skip-produce mode), validate the most recent trace.

    Returns a result dict with 'ok', 'evidence', and 'errors' keys.
    """
    from langfuse import Langfuse

    lf = Langfuse()
    from_ts = datetime.now(UTC) - timedelta(minutes=lookback_minutes)

    try:
        traces_page = lf.api.trace.list(
            name="voice-session",
            from_timestamp=from_ts,
            order_by="timestamp.desc",
            limit=10,
        )
    except Exception as e:
        return {"ok": False, "evidence": None, "errors": [f"API call failed: {e}"]}
    finally:
        lf.flush()

    traces_data = getattr(traces_page, "data", []) or []

    if not traces_data:
        return {
            "ok": False,
            "evidence": None,
            "errors": [f"No voice-session traces found in last {lookback_minutes} minutes"],
        }

    # Filter by expected session_id if provided
    if expected_session_id:
        matching = [
            t for t in traces_data
            if getattr(t, "session_id", "") == expected_session_id
        ]
        if not matching:
            return {
                "ok": False,
                "evidence": None,
                "errors": [
                    f"No trace with session_id={expected_session_id!r} found "
                    f"(found {len(traces_data)} other voice-session traces)"
                ],
            }
        trace = matching[0]
    else:
        # Validate the most recent trace
        trace = traces_data[0]

    errors: list[str] = []

    # Check service attribution
    user_id = getattr(trace, "user_id", None)
    if user_id != "voice-agent":
        errors.append(f"user_id={user_id!r}, expected 'voice-agent'")

    session_id = getattr(trace, "session_id", None) or ""
    if not session_id.startswith("voice-"):
        errors.append(f"session_id={session_id!r} does not match 'voice-*' pattern")

    tags = getattr(trace, "tags", None) or []
    if "voice" not in tags:
        errors.append("Missing 'voice' tag")
    if "call-lifecycle" not in tags:
        errors.append("Missing 'call-lifecycle' tag")

    # Build evidence summary (redacted, no PII)
    trace_id = getattr(trace, "id", "unknown")
    evidence = {
        "trace_id": trace_id,
        "session_id": session_id,
        "user_id": user_id,
        "tags": tags,
        "traces_found": len(traces_data),
    }

    return {"ok": len(errors) == 0, "evidence": evidence, "errors": errors}


def check_compose_service_name() -> bool:
    """Static check: verify OTEL_SERVICE_NAME is associated with voice-agent in compose.yml."""
    compose_path = Path(__file__).resolve().parent.parent / "compose.yml"
    if not compose_path.exists():
        print("WARNING: compose.yml not found; skipping static OTEL check")
        return True

    content = compose_path.read_text()
    if re.search(r"OTEL_SERVICE_NAME.*voice-agent", content):
        print("OK: OTEL_SERVICE_NAME=voice-agent found in compose.yml")
        return True

    print("WARNING: OTEL_SERVICE_NAME=voice-agent not found in compose.yml")
    return False


def main() -> None:
    """Run the voice trace validation gate."""
    args = parse_args()

    print("=" * 60)
    print("Voice Trace Validation Gate")
    print("=" * 60)
    print()

    # Set environment variables for Langfuse client instances used later
    os.environ["LANGFUSE_HOST"] = args.host
    os.environ["LANGFUSE_PUBLIC_KEY"] = args.public_key
    os.environ["LANGFUSE_SECRET_KEY"] = args.secret_key

    # Step 1: Connectivity check
    print("[1/5] Checking Langfuse connectivity...")
    if not check_langfuse_connectivity(args.host, args.public_key, args.secret_key):
        sys.exit(1)
    print()

    # Step 2: Static compose check
    print("[2/5] Checking OTEL_SERVICE_NAME in compose.yml...")
    check_compose_service_name()
    print()

    # Step 3: Produce trace (unless --skip-produce)
    produced_session_id: str | None = None
    if not args.skip_produce:
        print("[3/5] Producing voice-session trace...")
        try:
            produced_session_id = produce_voice_trace()
        except Exception as e:
            print(f"WARNING: Could not produce trace: {e}")
            print("    Continuing with validation of existing traces...")
        print()

        # Step 4: Wait for ingestion
        print("[4/5] Waiting for ingestion...")
        wait_for_ingestion(3)
        print()
    else:
        print("[3/5] Skipping trace production (--skip-produce)")
        print("[4/5] Skipping wait")
        print()

    # Step 5: Validate
    print("[5/5] Validating voice-session traces...")
    result = validate_traces(args.lookback_minutes, expected_session_id=produced_session_id)

    if result["evidence"]:
        print()
        print("Evidence Summary (redacted):")
        evidence = result["evidence"]
        print(f"  trace_id:     {evidence['trace_id']}")
        print(f"  session_id:   {evidence['session_id']}")
        print(f"  user_id:      {evidence['user_id']}")
        print(f"  tags:         {evidence['tags']}")
        print(f"  traces_found: {evidence['traces_found']}")

    print()
    if result["ok"]:
        print("PASS: Voice trace validation gate passed")
        sys.exit(0)
    else:
        print("FAIL: Voice trace validation gate failed")
        for err in result["errors"]:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
