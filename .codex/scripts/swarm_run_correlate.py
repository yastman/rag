#!/usr/bin/env python3
"""Build a compact run dossier from swarm worker metadata files.

Usage:
    uv run python .codex/scripts/swarm_run_correlate.py <worker-or-run-prefix>
        [--worktree DIR] [--output dossier.json]

Given a worker name or run prefix (e.g. "worker-1551-swarm-helpers"), this
script scans a swarm worktree for:
  - .signals/launch-${PREFIX}*.json
  - .signals/secretary-${PREFIX}*.json
  - .signals/wakeup-${PREFIX}*.json
  - .signals/DONE-${PREFIX}*.json  (and other signal files)
  - .codex/prompts/${PREFIX}* (worker prompt files)
  - logs/opencode-${PREFIX}*.log   (just stat info, not raw content)

and emits a compact JSON dossier with key metadata, timestamps, status, and
file references.  The dossier is safe to read into orchestrator context without
unbounded log scanning.

Purpose (issue #1551): replace manual artifact correlation with a deterministic
per-run dossier.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _find_files(worktree: Path, pattern_dir: str, glob_pattern: str) -> list[Path]:
    d = worktree / pattern_dir
    if not d.is_dir():
        return []
    files = sorted(d.glob(glob_pattern))
    return list(files)


def _stat_info(p: Path) -> dict[str, Any]:
    try:
        st = p.stat()
        return {
            "path": str(p),
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
        }
    except OSError:
        return {"path": str(p), "error": "stat failed"}


def _load_json_safe(p: Path) -> dict[str, Any] | None:
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        return {"_load_error": str(exc)}


def _safe_read_head(p: Path, lines: int = 20) -> str:
    """Read first *lines* lines of a text file safely."""
    try:
        with open(p, encoding="utf-8") as fh:
            return "".join(fh.readline() for _ in range(lines))
    except OSError as exc:
        return f"[read error: {exc}]"


def _extract_key_meta(data: dict[str, Any] | None, prefix: str) -> dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data.get("_load_error"), str):
        return {"_load_error": data["_load_error"]}
    # Pull key fields only — we want a compact dossier
    keys = {
        "launch": [
            "worker",
            "runner",
            "agent",
            "model",
            "variant",
            "started_at",
            "prompt_sha256",
            "issue",
            "required_skills",
            "prompt_file",
            "worktree",
            "route_check_confirmed",
        ],
        "wakeup": ["worker", "status", "tag", "sent_at", "signal_file"],
        "signal": [
            "status",
            "issue",
            "summary",
            "review_decision",
            "changed_files",
            "findings",
            "blockers_found",
            "blockers_resolved",
            "new_bugs",
            "verification_budget",
            "next_action",
            "ts",
        ],
        "secretary": ["issue", "title", "route", "status", "summary", "ts", "brief"],
    }
    kset = keys.get(prefix, [])
    if not kset:
        return {}
    return {k: data[k] for k in kset if k in data}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Swarm run correlator — build compact run dossier from metadata files"
    )
    parser.add_argument("prefix", type=str, help="Worker name or run prefix")
    parser.add_argument(
        "--worktree",
        "-w",
        type=Path,
        default=Path.cwd(),
        help="Worktree root directory (default: cwd)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output dossier JSON path (defaults to stdout)",
    )
    parser.add_argument(
        "--include-log-head",
        action="store_true",
        help="Include first 20 lines of the raw OpenCode log (off by default)",
    )
    args = parser.parse_args()

    wt = args.worktree.resolve()
    prefix = args.prefix

    # Collect files
    launch_files = _find_files(wt, ".signals", f"launch-{prefix}*.json")
    wakeup_files = _find_files(wt, ".signals", f"wakeup-{prefix}*.json")
    secretary_files = _find_files(wt, ".signals", f"secretary-{prefix}*.json")
    done_files = _find_files(wt, ".signals", f"DONE-{prefix}*.json")
    exit_files = _find_files(wt, ".signals", f"exit-{prefix}*.json")
    all_signal_files = _find_files(wt, ".signals", "*.json")

    prompt_files = _find_files(wt, ".codex/prompts", f"{prefix}*")

    log_files = _find_files(wt, "logs", f"opencode-{prefix}*.log")

    # Build dossier
    dossier: dict[str, Any] = {
        "format": "run_dossier_v1",
        "prefix": prefix,
        "worktree": str(wt),
        "generated_at": datetime.now(UTC).isoformat(),
    }

    # Launch metadata
    if launch_files:
        launch_data = _load_json_safe(launch_files[0])
        dossier["launch"] = _extract_key_meta(launch_data, "launch")
        dossier["launch"]["_file"] = str(launch_files[0])
    else:
        dossier["launch"] = None

    # Wakeup metadata
    dossier["wakeups"] = []
    for wf in wakeup_files:
        wdata = _load_json_safe(wf)
        meta = _extract_key_meta(wdata, "wakeup")
        meta["_file"] = str(wf)
        dossier["wakeups"].append(meta)

    # DONE/exit signals
    all_completion_files = done_files + exit_files
    dossier["completion_signals"] = []
    for cf in all_completion_files:
        cdata = _load_json_safe(cf)
        meta = _extract_key_meta(cdata, "signal")
        meta["_file"] = str(cf)
        dossier["completion_signals"].append(meta)

    # Secretary briefs (may have been inline in launch or separate file)
    dossier["secretary_briefs"] = []
    for sf in secretary_files:
        sdata = _load_json_safe(sf)
        meta = _extract_key_meta(sdata, "secretary")
        meta["_file"] = str(sf)
        dossier["secretary_briefs"].append(meta)

    # Prompt file info
    dossier["prompt_files"] = []
    for pf in prompt_files:
        info = _stat_info(pf)
        if args.include_log_head:
            info["head_lines"] = _safe_read_head(pf, 20)
        dossier["prompt_files"].append(info)

    # Log file info (stat only, not content)
    dossier["log_files"] = []
    for lf in log_files:
        info = _stat_info(lf)
        if args.include_log_head:
            info["head_lines"] = _safe_read_head(lf, 20)
        dossier["log_files"].append(info)

    # Summary stats
    log_total_bytes = sum(
        f.get("size_bytes", 0) for f in dossier["log_files"] if isinstance(f.get("size_bytes"), int)
    )
    dossier["summary"] = {
        "launch_exists": bool(launch_files),
        "wakeup_count": len(wakeup_files),
        "completion_signal_count": len(all_completion_files),
        "secretary_brief_count": len(secretary_files),
        "prompt_file_count": len(prompt_files),
        "log_file_count": len(log_files),
        "log_total_bytes": log_total_bytes,
        "signal_file_count": len(all_signal_files),
    }

    # Determine run status
    latest_status = "unknown"
    for meta in dossier["completion_signals"]:
        if meta.get("status"):
            latest_status = meta["status"]
    if wakeup_files and not dossier["completion_signals"]:
        for w in dossier["wakeups"]:
            if w.get("status"):
                latest_status = w["status"]
    dossier["inferred_status"] = latest_status

    # Output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(dossier, fh, indent=2, ensure_ascii=False)
        print(f"Dossier written to {args.output}", file=sys.stderr)
    else:
        json.dump(dossier, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
