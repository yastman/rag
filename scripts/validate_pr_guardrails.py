#!/usr/bin/env python3
"""Validate PR anti-regression guardrails.

Bounded canonical check used by swarm-acceptance for bugfix / duplicate /
recurrence / umbrella PRs. Checks:
  1. PR body contains required Bug class / Regression guardrail / Checks run fields.
  2. .github/bug-classes.yml contains the declared bug_class (if provided).
  3. changed_files includes a test or guardrail file (regression evidence).

Usage:
    python3 scripts/validate_pr_guardrails.py --pr <number> [--bug-class <class>]

Exit codes:
    0 — all checks pass
    1 — one or more checks failed (prints findings)
    2 — usage error
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BUG_CLASSES_FILE = REPO_ROOT / ".github" / "bug-classes.yml"

REQUIRED_PR_BODY_FIELDS = ["Bug class", "Regression guardrail", "Checks run"]


def _gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)  # nosec B603 B607 - fixed gh CLI command, no shell
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def validate(pr: int, bug_class: str | None = None) -> list[str]:
    findings: list[str] = []

    # 1. PR body fields
    try:
        body = _gh("pr", "view", str(pr), "--json", "body", "--jq", ".body")
    except RuntimeError as e:
        return [f"Cannot fetch PR body: {e}"]

    for field in REQUIRED_PR_BODY_FIELDS:
        if field not in body:
            findings.append(f"PR body missing required field: '{field}'")

    # 2. bug-classes.yml
    if bug_class:
        if not BUG_CLASSES_FILE.exists():
            findings.append(
                f"bug_class '{bug_class}' declared but .github/bug-classes.yml does not exist"
            )
        else:
            content = BUG_CLASSES_FILE.read_text(encoding="utf-8")
            if bug_class not in content:
                findings.append(f"bug_class '{bug_class}' not found in .github/bug-classes.yml")

    # 3. Regression evidence: at least one test/guardrail file in changed files
    try:
        files_json = _gh("pr", "view", str(pr), "--json", "files", "--jq", "[.files[].path]")
        changed_files: list[str] = json.loads(files_json)
    except (RuntimeError, json.JSONDecodeError):
        changed_files = []

    has_test = any(
        "test" in f or "guardrail" in f or f.endswith((".yml", ".yaml")) for f in changed_files
    )
    if changed_files and not has_test:
        findings.append(
            "No test or guardrail file found in changed_files — regression evidence required"
        )

    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--bug-class", default=None, help="Bug class to verify in registry")
    args = parser.parse_args()

    findings = validate(args.pr, args.bug_class)
    if findings:
        for f in findings:
            print(f"FAIL: {f}")
        sys.exit(1)
    else:
        print("OK: all PR guardrail checks passed")


if __name__ == "__main__":
    main()
