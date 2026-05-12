"""Sanitized latest-trace audit command for post-E2E Langfuse validation.

Runs after `make e2e-test-traces-core` to inspect the most recent traces,
report sanitized coverage metadata, and exit non-zero when required app
coverage is missing.

Usage:
    python scripts/e2e/langfuse_latest_trace_audit.py [--session SESSION] [--limit N] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langfuse import Langfuse

# Reuse contracts from the validator module to stay consistent.
from scripts.e2e.langfuse_trace_validator import (
    OBSERVATION_ALIAS_GROUPS,
    SCENARIO_CONTRACTS,
    SCORE_NAMES,
)


DEFAULT_TRACE_LIMIT = 20
DEFAULT_ARTIFACT_DIR = Path(".artifacts/langfuse-local-audit")

LITELLM_PROXY_TRACE_NAMES = {"litellm-acompletion", "litellm-completion"}


@dataclass(frozen=True)
class AuditTrace:
    """Sanitized trace metadata (no raw payloads)."""

    trace_id: str
    name: str
    tags: list[str]
    session_id: str | None
    timestamp: str | None
    observation_names: list[str]
    score_names: list[str]
    root_input_keys: list[str]
    root_output_keys: list[str]
    observation_count: int
    score_count: int
    is_proxy_noise: bool


@dataclass(frozen=True)
class TraceCoverage:
    """Coverage result for a single inspected trace."""

    trace: AuditTrace
    scenario_kind: str | None
    missing_observations: set[str] = field(default_factory=set)
    missing_scores: set[str] = field(default_factory=set)
    missing_root_input: bool = False
    missing_root_output: bool = False
    ok: bool = False


@dataclass(frozen=True)
class AuditResult:
    """Overall audit result."""

    inspected: list[TraceCoverage]
    proxy_noise_count: int
    app_trace_count: int
    timestamp: str
    session_marker: str | None
    artifact_path: Path | None
    ok: bool


def _langfuse_is_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _resolve_missing_observations(
    required_observations: set[str], span_names: set[str]
) -> set[str]:
    missing: set[str] = set()
    for required in required_observations:
        aliases = OBSERVATION_ALIAS_GROUPS.get(required, {required})
        if not (aliases & span_names):
            missing.add(required)
    return missing


# Sanitized key safelist for root input/output — never report raw payloads or secrets.
_ALLOWED_ROOT_KEYS = {
    "content_type",
    "query_preview",
    "query_hash",
    "query_len",
    "route",
    "answer_hash",
    "response_preview",
}


def _keys_if_dict(value: object) -> list[str]:
    if isinstance(value, dict):
        return sorted({k for k in value if k in _ALLOWED_ROOT_KEYS})
    return []


def sanitize_trace(raw: object) -> AuditTrace:
    """Build sanitized AuditTrace from a raw Langfuse trace object or dict."""
    if isinstance(raw, dict):
        data = raw
    else:
        # Object-like (SDK model)
        data = {
            "id": getattr(raw, "id", None),
            "name": getattr(raw, "name", None),
            "tags": getattr(raw, "tags", None) or [],
            "sessionId": getattr(raw, "sessionId", None),
            "timestamp": getattr(raw, "timestamp", None),
            "input": getattr(raw, "input", None),
            "output": getattr(raw, "output", None),
            "observations": getattr(raw, "observations", None) or [],
            "scores": getattr(raw, "scores", None) or [],
        }

    trace_id = str(data.get("id") or "unknown")
    name = str(data.get("name") or "")
    tags = list(data.get("tags") or [])
    session_id = data.get("sessionId") or None
    timestamp = data.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        timestamp = str(timestamp)

    raw_obs = data.get("observations") or []
    observation_names = []
    for obs in raw_obs:
        if isinstance(obs, dict):
            observation_names.append(str(obs.get("name") or ""))
        else:
            observation_names.append(str(getattr(obs, "name", "") or ""))

    raw_scores = data.get("scores") or []
    score_names = []
    for score in raw_scores:
        if isinstance(score, dict):
            score_names.append(str(score.get("name") or ""))
        else:
            score_names.append(str(getattr(score, "name", "") or ""))

    root_input = data.get("input")
    root_output = data.get("output")

    is_proxy_noise = name in LITELLM_PROXY_TRACE_NAMES

    return AuditTrace(
        trace_id=trace_id,
        name=name,
        tags=tags,
        session_id=session_id,
        timestamp=timestamp,
        observation_names=sorted({n for n in observation_names if n}),
        score_names=sorted({n for n in score_names if n}),
        root_input_keys=_keys_if_dict(root_input),
        root_output_keys=_keys_if_dict(root_output),
        observation_count=len(raw_obs),
        score_count=len(raw_scores),
        is_proxy_noise=is_proxy_noise,
    )


def _check_trace_coverage(trace: AuditTrace) -> TraceCoverage:
    """Determine coverage for an app trace against the strictest scenario contract."""
    if trace.is_proxy_noise:
        return TraceCoverage(
            trace=trace,
            scenario_kind=None,
            ok=True,
        )
    # Choose the contract that best matches this trace.
    scenario_kind = None
    required_observations: set[str] = set()
    required_scores: set[str] = set(SCORE_NAMES)

    for kind, contract in SCENARIO_CONTRACTS.items():
        trace_names = contract.get("trace_names", [])
        contract_tags = contract.get("tags", [])
        if trace.name in trace_names or any(t in trace.tags for t in contract_tags):
            scenario_kind = kind
            required_observations = set(contract.get("required_observations", set()))
            required_scores = set(contract.get("required_scores", set(SCORE_NAMES)))
            break

    if scenario_kind is None:
        # Unknown trace — treat as app trace with base requirements only.
        scenario_kind = "unknown"
        required_observations = {"telegram-rag-query", "telegram-rag-supervisor"}

    span_names = set(trace.observation_names)
    missing_obs = _resolve_missing_observations(required_observations, span_names)
    missing_scores = set(required_scores) - set(trace.score_names)

    missing_root_input = "query_hash" not in trace.root_input_keys
    missing_root_output = "answer_hash" not in trace.root_output_keys

    if missing_root_input:
        missing_obs.add("root_input")
    if missing_root_output:
        missing_obs.add("root_output")

    ok = not missing_obs and not missing_scores

    return TraceCoverage(
        trace=trace,
        scenario_kind=scenario_kind,
        missing_observations=missing_obs,
        missing_scores=missing_scores,
        missing_root_input=missing_root_input,
        missing_root_output=missing_root_output,
        ok=ok,
    )


def _fetch_traces_via_cli(
    *,
    limit: int = DEFAULT_TRACE_LIMIT,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch traces via `langfuse` CLI subprocess; returns list of trace dicts."""
    cmd = [
        "langfuse",
        "api",
        "traces",
        "list",
        "--limit",
        str(limit),
        "--order-by",
        "timestamp.desc",
        "--fields",
        "core,io,scores,observations,metrics",
        "--json",
    ]
    if session_id:
        cmd += ["--session-id", session_id]

    env = os.environ.copy()
    # Ensure LANGFUSE_HOST is honoured
    if os.getenv("LANGFUSE_BASE_URL") and not os.getenv("LANGFUSE_HOST"):
        env["LANGFUSE_HOST"] = os.getenv("LANGFUSE_BASE_URL", "")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )  # nosec B603
    if result.returncode != 0:
        raise RuntimeError(f"langfuse CLI failed (rc={result.returncode}): {result.stderr}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"langfuse CLI returned invalid JSON: {exc}") from exc

    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        # Some CLI versions wrap differently
        return [payload] if payload.get("id") else []
    if isinstance(payload, list):
        return payload
    return []


def _fetch_traces_via_sdk(
    *,
    limit: int = DEFAULT_TRACE_LIMIT,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch traces via Langfuse SDK; returns list of trace dicts."""
    langfuse = Langfuse()
    kwargs: dict[str, Any] = {
        "limit": limit,
        "order_by": "timestamp.desc",
    }
    if session_id:
        kwargs["session_id"] = session_id

    page = langfuse.api.trace.list(**kwargs)
    traces = page.data if hasattr(page, "data") else []

    out: list[dict[str, Any]] = []
    for t in traces:
        if isinstance(t, dict):
            out.append(t)
        else:
            # Convert object to dict via dataclass-like fields where possible
            out.append(
                {
                    "id": getattr(t, "id", None),
                    "name": getattr(t, "name", None),
                    "tags": getattr(t, "tags", None) or [],
                    "sessionId": getattr(t, "sessionId", None),
                    "timestamp": getattr(t, "timestamp", None),
                    "input": getattr(t, "input", None),
                    "output": getattr(t, "output", None),
                    "observations": getattr(t, "observations", None) or [],
                    "scores": getattr(t, "scores", None) or [],
                }
            )
    return out


def fetch_latest_traces(
    *,
    limit: int = DEFAULT_TRACE_LIMIT,
    session_id: str | None = None,
    prefer_cli: bool = True,
) -> list[AuditTrace]:
    """Fetch and sanitize the latest traces, preferring CLI when available."""
    errors: list[str] = []

    if prefer_cli:
        try:
            raw_traces = _fetch_traces_via_cli(limit=limit, session_id=session_id)
            return [sanitize_trace(t) for t in raw_traces]
        except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            errors.append(f"CLI path failed: {exc}")

    # SDK fallback
    if not _langfuse_is_configured():
        raise RuntimeError(
            "Langfuse is not configured (LANGFUSE_PUBLIC_KEY/SECRET_KEY missing) "
            f"and CLI path also failed: {'; '.join(errors)}"
        )

    raw_traces = _fetch_traces_via_sdk(limit=limit, session_id=session_id)
    return [sanitize_trace(t) for t in raw_traces]


def render_markdown(result: AuditResult) -> str:
    """Render deterministic markdown report."""
    lines: list[str] = [
        "# Langfuse Latest Trace Audit",
        "",
        f"- **Audit timestamp:** {result.timestamp}",
        f"- **Session marker:** {result.session_marker or '(none)'}",
        f"- **Artifact path:** {result.artifact_path}",
        f"- **Overall:** {'PASS' if result.ok else 'FAIL'}",
        "",
        "## Summary",
        "",
        f"- **Total inspected:** {len(result.inspected)}",
        f"- **App traces:** {result.app_trace_count}",
        f"- **Proxy noise (LiteLLM):** {result.proxy_noise_count}",
        "",
        "## Per-Trace Coverage",
        "",
    ]

    for cov in result.inspected:
        trace = cov.trace
        status = "PASS" if cov.ok else "FAIL"
        lines.append(f"### {trace.name} — `{trace.trace_id}`")
        lines.append("")
        lines.append(f"- **Status:** {status}")
        lines.append(f"- **Scenario:** {cov.scenario_kind or 'unknown'}")
        lines.append(f"- **Tags:** {', '.join(trace.tags) or '(none)'}")
        lines.append(f"- **Session:** {trace.session_id or '(none)'}")
        lines.append(f"- **Timestamp:** {trace.timestamp or '(none)'}")
        lines.append(
            f"- **Observations:** {trace.observation_count} ({', '.join(trace.observation_names) or '(none)'})"
        )
        lines.append(
            f"- **Scores:** {trace.score_count} ({', '.join(trace.score_names) or '(none)'})"
        )
        lines.append(f"- **Root input keys:** {', '.join(trace.root_input_keys) or '(none)'}")
        lines.append(f"- **Root output keys:** {', '.join(trace.root_output_keys) or '(none)'}")
        if trace.is_proxy_noise:
            lines.append("- **Classification:** proxy noise (LiteLLM)")
        lines.append("")
        if not cov.ok and not trace.is_proxy_noise:
            if cov.missing_observations:
                lines.append(
                    f"- **Missing observations:** {', '.join(sorted(cov.missing_observations))}"
                )
            if cov.missing_scores:
                lines.append(f"- **Missing scores:** {', '.join(sorted(cov.missing_scores))}")
            lines.append("")

    lines.append("## Required App Coverage Check")
    lines.append("")
    if result.ok:
        lines.append("All inspected app traces meet required coverage.")
    else:
        lines.append("**FAIL** — required app coverage is incomplete.")
    lines.append("")

    return "\n".join(lines)


def run_audit(
    *,
    session_id: str | None = None,
    limit: int = DEFAULT_TRACE_LIMIT,
    output_dir: Path = DEFAULT_ARTIFACT_DIR,
    prefer_cli: bool = True,
) -> AuditResult:
    """Run the full audit and write artifact."""
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d-%H%M%S")

    traces = fetch_latest_traces(limit=limit, session_id=session_id, prefer_cli=prefer_cli)

    inspected: list[TraceCoverage] = []
    proxy_noise_count = 0
    app_trace_count = 0
    overall_ok = True

    for trace in traces:
        if trace.is_proxy_noise:
            proxy_noise_count += 1
            inspected.append(
                TraceCoverage(
                    trace=trace,
                    scenario_kind=None,
                    ok=True,
                )
            )
            continue

        app_trace_count += 1
        cov = _check_trace_coverage(trace)
        inspected.append(cov)
        if not cov.ok:
            overall_ok = False

    # If there are zero app traces, the audit fails because we cannot confirm coverage.
    if app_trace_count == 0:
        overall_ok = False

    artifact_dir = output_dir / timestamp
    artifact_path = artifact_dir / "latest-traces.md"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    result = AuditResult(
        inspected=inspected,
        proxy_noise_count=proxy_noise_count,
        app_trace_count=app_trace_count,
        timestamp=timestamp,
        session_marker=session_id,
        artifact_path=artifact_path,
        ok=overall_ok,
    )

    artifact_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sanitized post-E2E Langfuse latest-trace audit",
    )
    parser.add_argument(
        "--session",
        dest="session_id",
        default=None,
        help="Session marker to filter traces",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_TRACE_LIMIT,
        help=f"Maximum traces to inspect (default {DEFAULT_TRACE_LIMIT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help=f"Artifact output directory (default {DEFAULT_ARTIFACT_DIR})",
    )
    parser.add_argument(
        "--sdk-only",
        action="store_true",
        help="Force SDK path instead of preferring CLI",
    )
    args = parser.parse_args(argv)

    try:
        result = run_audit(
            session_id=args.session_id,
            limit=args.limit,
            output_dir=args.output_dir,
            prefer_cli=not args.sdk_only,
        )
    except RuntimeError as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 1

    print(f"Artifact written to: {result.artifact_path}")
    print(f"Overall: {'PASS' if result.ok else 'FAIL'}")
    print(f"  App traces: {result.app_trace_count}")
    print(f"  Proxy noise: {result.proxy_noise_count}")

    for cov in result.inspected:
        if cov.trace.is_proxy_noise:
            print(f"  [PROXY] {cov.trace.name} ({cov.trace.trace_id})")
        else:
            status = "PASS" if cov.ok else "FAIL"
            print(f"  [{status}] {cov.trace.name} ({cov.trace.trace_id})")
            if cov.missing_observations:
                print(
                    f"         Missing observations: {', '.join(sorted(cov.missing_observations))}"
                )
            if cov.missing_scores:
                print(f"         Missing scores: {', '.join(sorted(cov.missing_scores))}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
