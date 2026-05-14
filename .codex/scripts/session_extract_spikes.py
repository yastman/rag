#!/usr/bin/env python3
"""Extract bounded JSON-serialisable snippets around token spikes from a session profile.

Usage:
    uv run python .codex/scripts/session_extract_spikes.py profile.json [threshold]

Reads a profile produced by session_log_profile.py, finds spike events whose
absolute token delta exceeds *threshold* (default 5000), and emits compact
snippets with bounded context and line references.  Purpose: give the
orchestrator focused spike evidence instead of raw full-profile JSON or
full-session transcripts.

Note: The profile already contains spike_jumps_over_threshold; this script lets
you re-filter at a different threshold without re-parsing the original JSONL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _bounded_snippets(
    timeline: list[dict[str, Any]], spike_lines: set[int], context: int = 3
) -> list[dict[str, Any]]:
    """Return bounded snippets around *spike_lines* with *context* entries each side."""
    snippets: list[dict[str, Any]] = []
    for idx, entry in enumerate(timeline):
        line = entry.get("line", 0)
        if line not in spike_lines:
            continue
        start = max(0, idx - context)
        end = min(len(timeline), idx + context + 1)
        snippets.append(
            {
                "spike_line": line,
                "spike_delta": entry.get("delta"),
                "spike_ts": entry.get("ts", ""),
                "context_before": timeline[start:idx],
                "spike_entry": entry,
                "context_after": timeline[idx + 1 : end],
            }
        )
    return snippets


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract bounded snippets around token spikes from a session profile"
    )
    parser.add_argument("profile", type=Path, help="Profile JSON from session_log_profile.py")
    parser.add_argument(
        "threshold",
        type=int,
        nargs="?",
        default=5000,
        help="Minimum absolute token delta to treat as a spike (default: 5000)",
    )
    parser.add_argument(
        "--context",
        "-c",
        type=int,
        default=3,
        help="Number of timeline entries of context each side (default: 3)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None, help="Output JSON path (defaults to stdout)"
    )
    args = parser.parse_args()

    with open(args.profile, encoding="utf-8") as fh:
        profile = json.load(fh)

    timeline = profile.get("token_timeline", [])
    if not timeline:
        print("No token timeline in profile — nothing to extract.", file=sys.stderr)
        sys.exit(1)

    all_jumps = profile.get("largest_token_jumps", [])
    spike_lines = {j["line"] for j in all_jumps if j["abs_delta"] > args.threshold}

    snippets = _bounded_snippets(timeline, spike_lines, context=args.context)

    result = {
        "format": "spike_snippets_v1",
        "threshold": args.threshold,
        "context_window": args.context,
        "total_spikes": len(spike_lines),
        "snippets": snippets,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"Snippets written to {args.output}", file=sys.stderr)
    else:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
