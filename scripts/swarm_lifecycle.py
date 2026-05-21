#!/usr/bin/env python3
"""Lifecycle state machine for swarm workers."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


VALID_STATES = [
    "active",
    "done",
    "reviewing",
    "fix_needed",
    "merged",
    "closed",
    "failed",
    "blocked",
]

ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "active": ["done", "failed", "blocked"],
    "done": ["reviewing"],
    "reviewing": ["fix_needed", "merged", "closed"],
    "fix_needed": ["active"],
    "blocked": ["active", "failed"],
    "failed": ["active"],
    "merged": [],
    "closed": [],
}


def validate_transition(current: str, target: str) -> bool:
    """Return True if transition from current to target is allowed."""
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    return target in allowed


def transition_worker(worker_path: Path, target_state: str) -> dict:
    """Read worker JSON, validate transition, update state and timestamp, write back.

    Returns the updated worker dict.
    Raises ValueError if transition is invalid.
    """
    data = json.loads(worker_path.read_text(encoding="utf-8"))
    current_state = data.get("state", "active")

    if not validate_transition(current_state, target_state):
        raise ValueError(f"invalid transition: {current_state} -> {target_state}")

    data["state"] = target_state
    data["updated_at"] = datetime.now(tz=UTC).isoformat()
    worker_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Transition a swarm worker to a new state.")
    parser.add_argument("worker_path", type=Path, help="Path to worker signal JSON file")
    parser.add_argument("target_state", type=str, help="Target state to transition to")
    args = parser.parse_args()

    if args.target_state not in VALID_STATES:
        print(f"ERROR: invalid state: {args.target_state}")
        return 1

    try:
        result = transition_worker(args.worker_path, args.target_state)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot process worker file: {exc}")
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"OK: transitioned to {result['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
