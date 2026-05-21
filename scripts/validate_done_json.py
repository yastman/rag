***REMOVED***!/usr/bin/env python3
"""Validate a DONE JSON file against the expected schema for swarm workers.

Usage:
    python scripts/validate_done_json.py path/to/file.done.json
    echo '{"status": "DONE", ...}' | python scripts/validate_done_json.py -
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


REQUIRED_FIELDS: list[str] = [
    "status",
    "worker",
    "task",
    "worktree",
    "branch",
    "head_sha",
    "reserved_files",
    "changed_files",
    "superpowers_used",
    "skipped_superpowers",
    "evidence_commands",
]

VALID_STATUSES: set[str] = {"DONE", "FAILED", "BLOCKED"}

LIST_OF_STRINGS_FIELDS: list[str] = [
    "reserved_files",
    "changed_files",
    "superpowers_used",
    "skipped_superpowers",
    "evidence_commands",
]


def validate(data: Any) -> list[str]:
    """Validate *data* against the DONE JSON schema.

    Returns a list of error messages (empty means valid).
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["root must be a JSON object"]

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    if "status" in data and data["status"] not in VALID_STATUSES:
        errors.append(
            f"invalid status: {data['status']!r} (must be one of {sorted(VALID_STATUSES)})"
        )

    for field in LIST_OF_STRINGS_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if not isinstance(value, list):
            errors.append(f"{field} must be a list, got {type(value).__name__}")
        else:
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    errors.append(f"{field}[{i}] must be a string, got {type(item).__name__}")

    return errors


def main(argv: list[str] | None = None) -> int:
    """Entry point for CLI invocation."""
    parser = argparse.ArgumentParser(
        description="Validate a DONE JSON file against the swarm worker schema."
    )
    parser.add_argument(
        "file",
        help="Path to DONE JSON file, or '-' for stdin.",
    )
    args = parser.parse_args(argv)

    try:
        if args.file == "-":
            content = sys.stdin.read()
        else:
            with open(args.file, encoding="utf-8") as f:
                content = f.read()
    except OSError as exc:
        print(f"ERROR: cannot read file: {exc}", file=sys.stderr)
        return 1

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 1

    errors = validate(data)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
