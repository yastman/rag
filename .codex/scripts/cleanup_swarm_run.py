#!/usr/bin/env python3
"""Clean up swarm run artifacts after an accepted worker signal.

Usage:
    uv run python .codex/scripts/cleanup_swarm_run.py <worker-or-prefix>
        [--worktree DIR] [--dry-run] [--archive-dir DIR]

After the orchestrator accepts a worker's DONE signal, this script safely
removes or archives:
  - Large raw OpenCode TUI logs (logs/opencode-${PREFIX}*.log)
  - Worker prompt copies (.codex/prompts/${PREFIX}*)
  - Intermediate/tmp files from swarm runs
  - Closes the worker tmux window (when applicable)

It preserves:
  - Accepted signal files (.signals/DONE-${PREFIX}*.json, .signals/launch-*, etc.)
  - Compact artifacts produced by issue #1551 helpers
  - The worktree itself

Safety features:
  - Dry-run mode (default prints what would be done)
  - Requires explicit --execute flag for actual cleanup
  - Never removes .signals/ directory content
  - Archived files go to an archive directory, not deleted (default: .signals/archive/)

Purpose (issue #1551): eliminate clutter and large log files from completed
swarm runs while preserving all accepted artifacts and signals.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 — tmux window management, checked via shutil.which()
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# Files/dirs to clean up (relative to worktree root)
CLEANUP_PATTERNS = [
    ("logs/", "opencode-${PREFIX}*.log"),
    (".codex/prompts/", "${PREFIX}*"),
]

# Directories/files that are NEVER removed
PROTECTED_PATHS = [
    ".signals/",
]

# Minimum file size (bytes) for log cleanup consideration
MIN_LOG_BYTES = 1024  # only clean logs > 1KB


def _find_files(worktree: Path, pattern_dir: str, glob_pattern: str) -> list[Path]:
    d = worktree / pattern_dir
    if not d.is_dir():
        return []
    return sorted(d.glob(glob_pattern))


def _plan_actions(worktree: Path, prefix: str) -> list[dict[str, Any]]:
    """Build a list of planned cleanup actions without executing them."""
    actions: list[dict[str, Any]] = []

    for pattern_dir, glob_tmpl in CLEANUP_PATTERNS:
        glob_pat = glob_tmpl.replace("${PREFIX}", prefix)
        files = _find_files(worktree, pattern_dir, glob_pat)

        for f in files:
            resolved = str(f.resolve())
            # Skip protected paths
            if any(resolved.startswith(str((worktree / p).resolve())) for p in PROTECTED_PATHS):
                continue

            # Skip files that are too small to be worth cleaning
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            if pattern_dir.startswith("logs") and size < MIN_LOG_BYTES:
                continue

            actions.append(
                {
                    "type": "archive",
                    "path": resolved,
                    "size_bytes": size,
                    "reason": f"Cleanup pattern: {pattern_dir}{glob_pat}",
                }
            )

    return actions


def _execute_actions(actions: list[dict[str, Any]], archive_dir: Path) -> list[dict[str, Any]]:
    """Execute cleanup actions, archiving files instead of deleting them."""
    results: list[dict[str, Any]] = []
    archive_dir.mkdir(parents=True, exist_ok=True)

    for action in actions:
        src = Path(action["path"])
        if not src.exists():
            results.append({**action, "status": "skipped", "reason": "file missing"})
            continue

        # Create a safe archive name with timestamp
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"{ts}_{src.name}"
        dst = archive_dir / archive_name

        try:
            shutil.move(str(src), str(dst))
            results.append({**action, "status": "archived", "archived_to": str(dst)})
        except OSError as exc:
            results.append({**action, "status": "error", "error": str(exc)})

    return results


def _close_tmux_window(worker_name: str, dry_run: bool = False) -> dict[str, Any]:
    """Attempt to close the tmux window associated with a worker.

    Uses the canonical `tmux kill-window` command. This is a best-effort
    operation — workers may have already exited, or tmux may not be available.
    """
    if not shutil.which("tmux"):
        return {"action": "close_tmux_window", "status": "skipped", "reason": "tmux not available"}

    if dry_run:
        # Try to find the window
        try:
            result = subprocess.run(  # nosec B603 B607 — hardcoded cmd, tmux checked via which()
                ["tmux", "list-windows", "-F", "#{window_name}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            windows = result.stdout.strip().split("\n")
            matching = [w for w in windows if worker_name in w]
            if matching:
                return {
                    "action": "close_tmux_window",
                    "status": "would_close",
                    "matching_windows": matching,
                }
            return {
                "action": "close_tmux_window",
                "status": "skipped",
                "reason": "no matching tmux window found",
            }
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"action": "close_tmux_window", "status": "error", "error": str(exc)}
    else:
        # Actually close matching windows
        try:
            result = subprocess.run(  # nosec B603 B607 — hardcoded cmd
                ["tmux", "list-windows", "-F", "#{window_name}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            windows = result.stdout.strip().split("\n")
            matching = [w for w in windows if worker_name in w]
            closed = []
            for w in matching:
                subprocess.run(  # nosec B603 B607 — hardcoded cmd, window name from tmux
                    ["tmux", "kill-window", "-t", w],
                    capture_output=True,
                    timeout=10,
                )
                closed.append(w)
            return {
                "action": "close_tmux_window",
                "status": "closed" if closed else "none_found",
                "closed_windows": closed,
            }
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"action": "close_tmux_window", "status": "error", "error": str(exc)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Swarm run cleaner — safely archive worker artifacts after accepted signal"
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
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview actions without executing (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform cleanup (required for real cleanup)",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Archive directory (default: .signals/archive/ in worktree)",
    )
    parser.add_argument(
        "--no-tmux-close", action="store_true", help="Skip tmux window close attempt"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output action report JSON path (defaults to stdout)",
    )
    args = parser.parse_args()

    wt = args.worktree.resolve()
    prefix = args.prefix
    archive_dir = args.archive_dir or wt / ".signals" / "archive"

    # Check if this is an accepted run — look for a DONE signal with status "done"
    done_files = _find_files(wt, ".signals", f"DONE-{prefix}*.json")
    if done_files:
        try:
            with open(done_files[0], encoding="utf-8") as fh:
                done_data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            done_data = {}
        signal_status = done_data.get("status", "unknown")
        if signal_status != "done" and not args.execute:
            print(
                f"Warning: latest DONE signal status is '{signal_status}', not 'done'. "
                f"Use --execute to force cleanup.",
                file=sys.stderr,
            )

    actions = _plan_actions(wt, prefix)
    results: list[dict[str, Any]] = []

    if args.execute:
        results = _execute_actions(actions, archive_dir)
    else:
        results = [
            {
                **a,
                "status": "would_archive",
                "archived_to": f"would be: {archive_dir / a['path'].split('/')[-1]}",
            }
            for a in actions
        ]

    # Tmux window close
    tmux_result = None
    if not args.no_tmux_close:
        dry_run_tmux = not args.execute
        tmux_result = _close_tmux_window(prefix, dry_run=dry_run_tmux)

    report: dict[str, Any] = {
        "format": "cleanup_report_v1",
        "prefix": prefix,
        "worktree": str(wt),
        "archive_dir": str(archive_dir),
        "dry_run": not args.execute,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_files_to_clean": len(actions),
        "results": results,
    }
    if tmux_result:
        report["tmux_window"] = tmux_result

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"Cleanup report written to {args.output}", file=sys.stderr)
    else:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
