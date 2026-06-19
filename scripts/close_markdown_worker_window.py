#!/usr/bin/env python3
"""Close a Markdown-first worker tmux window after its report is accepted."""

from __future__ import annotations

import argparse
import subprocess  # nosec B404 - internal tmux tooling, fixed argv, no shell
import sys


FORBIDDEN_PREFIXES = ("orch-", "orchestrator")


def tmux_output(args: list[str]) -> str:
    result = subprocess.run(["tmux", *args], text=True, capture_output=True, check=False)  # nosec B603 B607 - fixed "tmux" argv, no shell=True, internal use
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def parse_windows(session: str | None) -> list[tuple[str, str]]:
    target = session or ""
    args = ["list-windows", "-F", "#{window_id}\t#{window_name}"]
    if target:
        args[1:1] = ["-t", target]
    windows: list[tuple[str, str]] = []
    for line in tmux_output(args).splitlines():
        if not line.strip():
            continue
        window_id, _, name = line.partition("\t")
        windows.append((window_id, name))
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely close a tmux window whose name exactly matches a Markdown worker name."
    )
    parser.add_argument("worker", help="Exact worker/window name from the DONE line.")
    parser.add_argument(
        "--session", help="tmux session to inspect. Defaults to current tmux session."
    )
    parser.add_argument(
        "--missing-ok",
        action="store_true",
        help="Return success when the worker window is already absent.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the matched window without closing it."
    )
    args = parser.parse_args()

    worker = args.worker.strip()
    if not worker:
        print("worker name is required", file=sys.stderr)
        return 2
    if worker.startswith(FORBIDDEN_PREFIXES):
        print(f"refusing to close orchestrator-like window: {worker}", file=sys.stderr)
        return 2

    matches = [
        (window_id, name) for window_id, name in parse_windows(args.session) if name == worker
    ]
    if not matches:
        message = f"worker_window_missing={worker}"
        print(message)
        return 0 if args.missing_ok else 1
    if len(matches) > 1:
        print(f"ambiguous worker window name {worker}: {matches}", file=sys.stderr)
        return 2

    window_id, name = matches[0]
    if args.dry_run:
        print(f"worker_window_match={name} window_id={window_id}")
        return 0

    tmux_output(["kill-window", "-t", window_id])
    print(f"worker_window_closed={name} window_id={window_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
