#!/usr/bin/env python3
"""Strip ANSI, find byte-offset markers, and return bounded snippets from OpenCode logs.

Usage:
    uv run python .codex/scripts/opencode_log_markers.py <opencode-log> [options]

Scans an OpenCode TUI (terminal UI) log file and:
  - Strips ANSI escape sequences
  - Locates important markers: DONE, FAILED, BLOCKED, swarm_notify_orchestrator,
    validators, errors, exceptions, tracebacks
  - For each marker, returns a bounded snippet (±N lines context) with byte
    offsets and line numbers
  - Supports output as compact JSON or human-readable text

Purpose (issue #1551): prevents agents from ever tailing/rg-ing raw TUI logs
which can dump huge ANSI-bloated chunks into context.  Instead, this tool
produces deterministic, bounded marker summaries.

Markers searched (case-sensitive):
  - swarm_notify_orchestrator
  - DONE JSON / "DONE"
  - FAILED / BLOCKED
  - error / Error / ERROR
  - exception / traceback
  - validator / acceptance / precheck
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


# Canonical markers to search for (regex, label)
MARKER_PATTERNS: list[tuple[str, str]] = [
    (r"swarm_notify_orchestrator", "orchestrator_wakeup"),
    (r'"status"\s*:\s*"DONE"', "DONE_status"),
    (r'"status"\s*:\s*"done"', "done_status"),
    (r'"status"\s*:\s*"FAILED"', "FAILED_status"),
    (r'"status"\s*:\s*"BLOCKED"', "BLOCKED_status"),
    (r'"status"\s*:\s*"blocked"', "blocked_status"),
    (r'"status"\s*:\s*"failed"', "failed_status"),
    (
        r"\bacceptance\b.*\bprecheck\b",
        "acceptance_precheck",
    ),
    (
        r"\bprecheck\b.*\bacceptance\b",
        "acceptance_precheck",
    ),
    (r"\bvalidator\b", "validator"),
    (r"\bTraceback \(most recent call last\)", "traceback"),
    (r"\bException\b", "exception"),
    (r"\bError\b", "error"),
    (r"\bERROR\b", "ERROR"),
    (r'"review_decision"\s*:\s*"blockers"', "review_blockers"),
    (r'"review_decision"\s*:\s*"clean"', "review_clean"),
    (r'"review_decision"\s*:\s*"escalate"', "review_escalate"),
]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
ANSI_CSI_ESC = re.compile(r"\x1b\][^\x07]*\x07")  # OSC sequences (title, etc.)


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from *text*."""
    return ANSI_CSI_ESC.sub("", ANSI_RE.sub("", text))


def find_markers(lines: list[str], patterns: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Search *lines* (after possible ANSI stripping) for each pattern.

    Returns a list of marker dicts with line number, byte offset, matched text,
    pattern label, and bounded snippet.
    """
    markers: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        for pat, label in patterns:
            m = re.search(pat, line)
            if m:
                markers.append(
                    {
                        "line": i,
                        "label": label,
                        "pattern": pat,
                        "matched_text": m.group(0),
                        "full_line": line.rstrip(),
                    }
                )
    return markers


def extract_snippets(
    lines: list[str], markers: list[dict[str, Any]], context: int = 5
) -> list[dict[str, Any]]:
    """For each marker, attach bounded context (±*context* lines)."""
    snippets: list[dict[str, Any]] = []
    for mk in markers:
        ln = mk["line"]
        start = max(0, ln - context - 1)
        end = min(len(lines), ln + context)
        snippets.append(
            {
                "marker": mk,
                "context_before": lines[start : ln - 1],
                "marker_line": lines[ln - 1].rstrip(),
                "context_after": lines[ln:end],
                "byte_offset_start": sum(len(s) for s in lines[:start])
                if start < len(lines)
                else 0,
                "byte_offset_end": sum(len(s) for s in lines[:end])
                if end <= len(lines)
                else sum(len(s) for s in lines),
            }
        )
    return snippets


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="OpenCode log marker scanner — strip ANSI, find markers, emit bounded snippets"
    )
    parser.add_argument("log_file", type=Path, help="OpenCode TUI log file path")
    parser.add_argument(
        "--context",
        "-c",
        type=int,
        default=5,
        help="Lines of context around each marker (default: 5)",
    )
    parser.add_argument(
        "--no-strip",
        action="store_true",
        help="Skip ANSI stripping (useful if log is already clean)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None, help="Output JSON path (defaults to stdout)"
    )
    parser.add_argument(
        "--summary-only", action="store_true", help="Only emit marker counts, no snippets"
    )
    args = parser.parse_args()

    log_path = args.log_file
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(log_path, encoding="utf-8") as fh:
            raw_lines = fh.readlines()
    except OSError as exc:
        print(f"Error reading {log_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    lines = raw_lines if args.no_strip else [strip_ansi(line) for line in raw_lines]

    markers = find_markers(lines, MARKER_PATTERNS)
    snippets = extract_snippets(lines, markers, context=args.context)

    # Count by label
    label_counts: dict[str, int] = {}
    for mk in markers:
        label_counts[mk["label"]] = label_counts.get(mk["label"], 0) + 1

    result: dict[str, Any] = {
        "format": "opencode_markers_v1",
        "file": str(log_path.resolve()),
        "total_lines": len(lines),
        "total_bytes_raw": log_path.stat().st_size,
        "stripped_ansi": not args.no_strip,
        "context_window": args.context,
        "total_markers_found": len(markers),
        "marker_counts": label_counts,
    }

    if args.summary_only:
        result["snippets"] = []
    else:
        result["snippets"] = snippets

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"Markers written to {args.output}", file=sys.stderr)
    else:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
