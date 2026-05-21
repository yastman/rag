#!/usr/bin/env python3
"""Guard against overlapping file reservations across active swarm workers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def check_overlaps(
    new_worker: dict, active_workers: list[dict], allow_sequential: bool = False
) -> list[dict]:
    """Check if new_worker's reserved_files overlap with any active workers.

    Returns a list of overlap details: [{worker_id, overlapping_files}].
    If allow_sequential is True and the conflicting worker has
    sequential=True, that overlap is permitted.
    """
    new_files = set(new_worker.get("reserved_files", []))
    overlaps: list[dict] = []

    for worker in active_workers:
        if allow_sequential and worker.get("sequential"):
            continue
        existing_files = set(worker.get("reserved_files", []))
        common = new_files & existing_files
        if common:
            overlaps.append(
                {
                    "worker_id": worker["worker_id"],
                    "overlapping_files": sorted(common),
                }
            )

    return overlaps


def load_registry(path: Path) -> list[dict]:
    """Load active workers from a JSONL registry file."""
    workers: list[dict] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line:
            workers.append(json.loads(line))
    return workers


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for overlapping file reservations across swarm workers."
    )
    parser.add_argument(
        "--new-worker", type=Path, required=True, help="Path to new worker JSON file"
    )
    parser.add_argument(
        "--registry", type=Path, required=True, help="Path to active workers JSONL registry"
    )
    parser.add_argument(
        "--allow-sequential",
        action="store_true",
        default=False,
        help="Permit overlaps with workers marked sequential",
    )
    args = parser.parse_args()

    try:
        new_worker = json.loads(args.new_worker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read new-worker file: {exc}")
        return 1

    try:
        active_workers = load_registry(args.registry)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read registry file: {exc}")
        return 1

    overlaps = check_overlaps(new_worker, active_workers, allow_sequential=args.allow_sequential)

    if overlaps:
        print("OVERLAP DETECTED:")
        for overlap in overlaps:
            print(f"  - worker {overlap['worker_id']}: {overlap['overlapping_files']}")
        return 1

    print("OK: no overlapping reservations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
