#!/usr/bin/env python3
"""Parse a Codex rollout JSONL log and emit a compact session profile as JSON.

Usage:
    uv run python .codex/scripts/session_log_profile.py <codex-rollout.jsonl> [--output profile.json]

Output: compact JSON with:
  - Token timeline: per-event token counts with line/timestamp refs
  - Largest token jumps: events where token delta exceeded thresholds
  - Tool calls: count, output sizes, and suspicious patterns
  - Suspicious commands: repeated polling, large output volumes
  - Summary statistics

Purpose (issue #1551): Codex/OpenCode orchestrator can consume this profile
instead of reading raw JSONL transcripts, saving context and avoiding accidental
large-dump incidents.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAX_OUTPUT_BYTES = 500_000  # flag any tool output exceeding this
MAX_DELTA_TOKENS = 5_000  # flag token jumps exceeding this
SUSPICIOUS_COMMAND_PATTERNS = (
    "--print-logs",
    "tail -f",
    "cat ",
    "rg ",
    "grep ",
    "find ",
)


@dataclass
class _Event:
    line: int
    ts: str
    role: str
    token_count: int | None
    delta: int | None
    tool_name: str | None
    tool_input_str: str | None
    output_bytes: int | None
    warnings: list[str] = field(default_factory=list)


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from *text*."""
    # minimal regex — full ANSI stripping is complex; this covers common ESC[ codes
    import re

    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text).rstrip()


def _parse_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                # corrupted line — skip but note in output
                records.append({"_parse_error": True, "_raw": stripped[:200]})
    return records


def _token_from(rec: dict[str, Any]) -> int | None:
    """Best-effort extract token count from a Codex JSONL record.

    Codex records come from the Anthropic API streaming format.  Typical paths:

    * message_start.message.usage.input_tokens → int
    * message_delta.usage.output_tokens → int
    * content_block_start / content_block_delta → may carry usage
    * Defaults: check rec['usage'], rec.get('token_count'), etc.
    """
    # message_start in Anthropic streaming
    ms = rec.get("message_start", {})
    if isinstance(ms, dict):
        msg = ms.get("message", {})
        if isinstance(msg, dict):
            usage = msg.get("usage", {})
            if isinstance(usage, dict):
                inp = usage.get("input_tokens")
                if isinstance(inp, int):
                    return inp

    # message_delta
    md = rec.get("message_delta", {})
    if isinstance(md, dict):
        usage = md.get("usage", {})
        if isinstance(usage, dict):
            out = usage.get("output_tokens")
            if isinstance(out, int):
                return out

    # flat usage field (OpenAI-style records)
    usage = rec.get("usage", {})
    if isinstance(usage, dict):
        tot = usage.get("total_tokens")
        if isinstance(tot, int):
            return tot

    # heuristic: token_count key
    tc = rec.get("token_count")
    if isinstance(tc, int):
        return tc

    return None


def _tool_info(rec: dict[str, Any]) -> tuple[str | None, int | None]:
    """Return (tool_name, output_bytes) from a Codex JSONL record.

    Codex tool-use records typically have 'content_block_start' or
    'tool_result' keys with 'content' or 'output' sub-keys.
    """
    # Anthropic-style tool_use
    cbs = rec.get("content_block_start", {})
    if isinstance(cbs, dict):
        cb = cbs.get("content_block", {})
        if isinstance(cb, dict) and cb.get("type") == "tool_use":
            return (cb.get("name"), None)

    # tool result with content
    tr = rec.get("tool_result", {})
    if isinstance(tr, dict):
        content = tr.get("content", "")
        if isinstance(content, (str, list)):
            if isinstance(content, list):
                content = json.dumps(content)
            return (None, len(content.encode("utf-8")))

    # Generic tool output
    output = rec.get("output")
    if isinstance(output, str):
        return (None, len(output.encode("utf-8")))

    return (None, None)


def _make_profile(records: list[dict[str, Any]]) -> dict[str, Any]:
    events: list[_Event] = []
    prev_tokens: int | None = None
    tool_calls: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []

    for idx, rec in enumerate(records, start=1):
        if rec.get("_parse_error"):
            events.append(
                _Event(
                    line=idx,
                    ts="",
                    role="parse_error",
                    token_count=0,
                    delta=0,
                    tool_name=None,
                    tool_input_str=None,
                    output_bytes=None,
                )
            )
            continue

        ts = str(rec.get("timestamp", rec.get("ts", "")))
        role = str(rec.get("role", rec.get("type", "")))

        tc = _token_from(rec)
        tool_name, out_bytes = _tool_info(rec)
        warnings: list[str] = []

        delta = None
        if tc is not None and prev_tokens is not None:
            delta = tc - prev_tokens

        if tool_name is not None or out_bytes is not None:
            tool_calls.append(
                {
                    "line": idx,
                    "ts": ts,
                    "tool_name": tool_name,
                    "output_bytes": out_bytes,
                }
            )

        # Suspicious command patterns
        if tool_name:
            inp_str = json.dumps(rec.get("input", rec.get("arguments", {})))
            for pat in SUSPICIOUS_COMMAND_PATTERNS:
                if pat.lower() in inp_str.lower():
                    suspicious.append(
                        {
                            "line": idx,
                            "ts": ts,
                            "reason": f"Command pattern '{pat}' detected in tool input",
                            "tool": tool_name,
                        }
                    )
                    break

        # Large output
        if out_bytes and out_bytes > MAX_OUTPUT_BYTES:
            warnings.append(f"Output exceeds {MAX_OUTPUT_BYTES} bytes ({out_bytes})")
            suspicious.append(
                {
                    "line": idx,
                    "ts": ts,
                    "reason": f"Tool output size {out_bytes} > {MAX_OUTPUT_BYTES}",
                    "tool": tool_name,
                }
            )

        events.append(
            _Event(
                line=idx,
                ts=ts,
                role=role,
                token_count=tc,
                delta=delta,
                tool_name=tool_name,
                tool_input_str=None,
                output_bytes=out_bytes,
                warnings=warnings,
            )
        )
        if tc is not None:
            prev_tokens = tc

    # Build token timeline
    timeline: list[dict[str, Any]] = []
    for e in events:
        entry: dict[str, Any] = {"line": e.line, "ts": e.ts}
        if e.token_count is not None:
            entry["tokens"] = e.token_count
        if e.delta is not None:
            entry["delta"] = e.delta
        if e.role:
            entry["role"] = e.role
        if e.warnings:
            entry["warnings"] = e.warnings
        if entry.get("tokens") is not None or entry.get("delta") is not None:
            timeline.append(entry)

    # Largest token jumps (absolute delta)
    deltas = sorted(
        [(e.line, abs(e.delta), e.delta, e.ts) for e in events if e.delta is not None],
        key=lambda x: x[1],
        reverse=True,
    )
    largest_jumps = [
        {"line": line, "abs_delta": abs_d, "delta": d, "ts": ts}
        for line, abs_d, d, ts in deltas[:20]
    ]

    # Jumps exceeding threshold
    spike_jumps = [j for j in largest_jumps if j["abs_delta"] > MAX_DELTA_TOKENS]

    # Summary
    token_values = [tc for e in events if e.token_count is not None for tc in (e.token_count,)]
    total_records = len(records)
    total_tool_calls = len(tool_calls)
    total_output_bytes = sum((tc.get("output_bytes") or 0) for tc in tool_calls)

    return {
        "format": "session_profile_v1",
        "total_records": total_records,
        "total_events_with_tokens": len(token_values),
        "max_tokens": max(token_values) if token_values else 0,
        "min_tokens": min(token_values) if token_values else 0,
        "token_timeline": timeline,
        "largest_token_jumps": largest_jumps,
        "spike_jumps_over_threshold": spike_jumps,
        "threshold_delta_tokens": MAX_DELTA_TOKENS,
        "tool_calls_total": total_tool_calls,
        "tool_output_bytes_total": total_output_bytes,
        "tool_call_details": tool_calls,
        "suspicious_commands": suspicious,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Codex session log profiler — emit compact token/payload profile from JSONL"
    )
    parser.add_argument("input", type=Path, help="Codex rollout JSONL file")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output profile JSON path (defaults to stdout)",
    )
    args = parser.parse_args()

    records = _parse_jsonl(args.input)
    profile = _make_profile(records)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2, ensure_ascii=False)
        print(f"Profile written to {args.output}", file=sys.stderr)
    else:
        json.dump(profile, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
