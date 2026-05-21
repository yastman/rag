#!/usr/bin/env python3
"""Validate worker signal JSON for required fields, types, and policy compliance."""

from __future__ import annotations

import argparse
import json
import sys
from enum import Enum
from pathlib import Path


class SignalStatus(Enum):
    DONE = "DONE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class NextAction(Enum):
    review = "review"
    verify = "verify"
    merge = "merge"
    fix = "fix"
    create_followup_issue = "create_followup_issue"
    blocked_human_decision = "blocked_human_decision"
    abandon_and_replan = "abandon_and_replan"


REQUIRED_FIELDS = [
    "status",
    "branch",
    "base",
    "prompt_hash",
    "agent",
    "model",
    "reserved_files",
    "pr_files",
    "command_evidence",
]

DENIED_COMMAND_PATTERNS = [
    "rm -rf /",
    "sudo ",
    "chmod 777",
    ":(){ :|:& };:",
]

ALLOWED_PATH_PREFIXES = ["scripts/", "tests/", "src/", "docs/"]


def validate_signal(data: dict) -> list[str]:
    """Check signal data for structural validity. Returns list of error strings."""
    errors: list[str] = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    if errors:
        return errors

    # Check status enum
    valid_statuses = {s.value for s in SignalStatus}
    if data["status"] not in valid_statuses:
        errors.append(
            f"invalid status: {data['status']}; must be one of {sorted(valid_statuses)}"
        )

    # Check branch is non-empty string
    if not isinstance(data["branch"], str) or not data["branch"]:
        errors.append("branch must be a non-empty string")

    # Check reserved_files is list of strings
    if not isinstance(data["reserved_files"], list):
        errors.append("reserved_files must be a list")
    elif not all(isinstance(f, str) for f in data["reserved_files"]):
        errors.append("reserved_files must contain only strings")

    # Check pr_files is list of strings
    if not isinstance(data["pr_files"], list):
        errors.append("pr_files must be a list")
    elif not all(isinstance(f, str) for f in data["pr_files"]):
        errors.append("pr_files must contain only strings")

    # Check command_evidence is non-empty list
    if not isinstance(data["command_evidence"], list):
        errors.append("command_evidence must be a list")
    elif len(data["command_evidence"]) == 0:
        errors.append("command_evidence must not be empty")

    # Check pr_files is subset of reserved_files (scope drift)
    if (
        isinstance(data["pr_files"], list)
        and isinstance(data["reserved_files"], list)
        and not set(data["pr_files"]).issubset(set(data["reserved_files"]))
    ):
        drift = set(data["pr_files"]) - set(data["reserved_files"])
        errors.append(f"pr_files scope drift: {sorted(drift)} not in reserved_files")

    return errors


def check_policy(data: dict) -> list[str]:
    """Check signal data for policy violations (dangerous commands, disallowed paths)."""
    errors: list[str] = []

    # Check command evidence for denied patterns
    commands = data.get("command_evidence", [])
    if isinstance(commands, list):
        for cmd in commands:
            if isinstance(cmd, str):
                for pattern in DENIED_COMMAND_PATTERNS:
                    if pattern in cmd:
                        errors.append(f"denied command pattern found: {pattern!r} in {cmd!r}")

    # Check reserved_files for disallowed path prefixes
    files = data.get("reserved_files", [])
    if isinstance(files, list):
        for f in files:
            if isinstance(f, str) and not any(
                f.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES
            ):
                errors.append(f"path not in allowed prefixes: {f!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a swarm worker signal JSON file.")
    parser.add_argument("signal_file", type=Path, help="Path to the signal JSON file")
    args = parser.parse_args()

    try:
        data = json.loads(args.signal_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read signal file: {exc}")
        return 1

    errors = validate_signal(data)
    policy_errors = check_policy(data)
    all_errors = errors + policy_errors

    if all_errors:
        print("INVALID signal:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
