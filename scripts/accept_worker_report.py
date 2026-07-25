#!/usr/bin/env python3
"""Mechanical worker-report checks (#2305 P0).

This is a RAIL, not a decision-maker. It emits MECHANICAL FACTS about a worker's
Markdown report and nothing else. It must never print a semantic acceptance
verdict (``accepted`` / ``merge_ready``) and must never create a PR — that
decision belongs to the orchestrator (``swarm-acceptance``).

``schema-valid != accepted``: presence/structure checks are mechanical facts.

Usage:
    python3 scripts/accept_worker_report.py --report <path> --role <research|implementation|review-fix>

Output (key=value lines, shell-parseable):
    report_found=1
    report_path=<path>
    role=<role>
    required_fields_present=1|0
    missing_fields=<csv>          # only when some are missing
    verification_found=1|0
    forbidden_files_touched=0|<n>
    mechanical_checks_passed=1|0

- Strict mode (env ``KIRO_STRICT_REPORT=1``) also prints ``schema_valid=1|0``
- from the mechanical required-field presence check.

The required field set is sourced from ``worker_report_schema`` (single source
of truth), which the contract test pins to the steering contract.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess  # nosec B404
import sys
from pathlib import Path


# Forbidden path patterns a worker must not touch by default (mechanical check).
FORBIDDEN_PATTERNS: tuple[str, ...] = (
    ".env",
    ".pem",
    ".key",
    ".kiro/skills/",
    ".kiro/agents/",
)


def _load_schema():
    spec = importlib.util.spec_from_file_location(
        "worker_report_schema", Path(__file__).with_name("worker_report_schema.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_markdown_fields(text: str) -> set[str]:
    """Extract field names present in the Markdown report."""
    found: set[str] = set()

    fence_pattern = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)```", re.DOTALL)
    extra_text = "\n".join(m.group(1) for m in fence_pattern.finditer(text))
    combined = text + "\n" + extra_text

    for line in combined.splitlines():
        stripped = line.strip()
        m = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if m:
            header = re.sub(r"[^a-z0-9]+", "_", m.group(1).lower()).strip("_")
            found.add(header)
            continue
        m = re.match(r"^([a-z][a-z0-9_\-]*):\s*", stripped, re.IGNORECASE)
        if m:
            found.add(m.group(1).lower().replace("-", "_"))
            continue
        m = re.match(r"^-\s+([a-z][a-z0-9_\-]*):\s*", stripped, re.IGNORECASE)
        if m:
            found.add(m.group(1).lower().replace("-", "_"))
    return found


def extract_changed_files(text: str) -> list[str]:
    """Best-effort extraction of changed_files list values for the forbidden check."""
    files: list[str] = []
    lines = text.splitlines()
    in_block = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"(?i)^(?:[-*]\s*)?changed_files\s*:", stripped):
            in_block = True
            continue
        if in_block:
            m = re.match(r"^[-*]\s+(.+)$", stripped)
            if m:
                files.append(m.group(1).strip().strip("`"))
                continue
            # A new key or blank line ends the block.
            if not stripped or re.match(r"^[a-z][a-z0-9_\-]*\s*:", stripped, re.IGNORECASE):
                in_block = False
    return files


def forbidden_files_touched(text: str) -> list[str]:
    hits: list[str] = []
    for f in extract_changed_files(text):
        if any(pat in f for pat in FORBIDDEN_PATTERNS):
            hits.append(f)
    return hits


def diff_vs_report(
    reported: list[str], branch: str, repo_root: Path | None = None
) -> tuple[bool, list[str]]:
    """Compare reported changed_files against actual git diff for branch.

    Returns (match: bool, undeclared_files: list[str]).
    undeclared_files = files in git diff but NOT in the report.
    If git is unavailable or branch is empty, returns (True, []) — no facts to emit.
    """
    cwd = str(repo_root) if repo_root else None
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "diff", "--name-only", f"{branch}...HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except FileNotFoundError:
        return True, []  # git not available
    if result.returncode != 0:
        return True, []  # branch not found or not a git repo

    diff_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    reported_set = set(reported)
    undeclared = [f for f in diff_files if f not in reported_set]
    return not undeclared, undeclared


def close_window(worker_name: str) -> None:
    closer = Path(__file__).with_name("close_markdown_worker_window.py")
    subprocess.run([sys.executable, str(closer), worker_name], check=False)  # nosec B603


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit mechanical facts about a Markdown worker report (no verdict)."
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--role", required=True, choices=["research", "implementation", "review-fix", "pr-review"]
    )
    parser.add_argument("--close-window", metavar="WORKER_NAME")
    parser.add_argument(
        "--branch",
        default="",
        metavar="BASE_BRANCH",
        help=(
            "Base branch for git diff reconciliation (e.g. 'main', 'dev'). "
            "When provided, emits diff_files_match=1|0 and undeclared_files=<csv> "
            "by comparing git diff <branch>...HEAD against the report's changed_files."
        ),
    )
    args = parser.parse_args()

    if not args.report.exists():
        print("report_found=0")
        print(f"report_path={args.report}")
        print("mechanical_checks_passed=0")
        return 1

    print("report_found=1")
    print(f"report_path={args.report}")
    print(f"role={args.role}")

    text = args.report.read_text(encoding="utf-8")
    found = parse_markdown_fields(text)

    schema = _load_schema()
    required = schema.required_fields_for_role(args.role)
    missing = [f for f in required if f not in found]

    required_present = not missing
    print(f"required_fields_present={int(required_present)}")
    if missing:
        print(f"missing_fields={','.join(missing)}")

    verification_found = "verification_evidence" in found or "evidence_commands" in found
    print(f"verification_found={int(verification_found)}")

    forbidden = forbidden_files_touched(text)
    print(f"forbidden_files_touched={len(forbidden)}")
    if forbidden:
        print(f"forbidden_files={','.join(forbidden)}")

    checks_passed = required_present and verification_found and not forbidden

    # Diff-vs-report reconciliation (Acceptance Gate #4).
    # Emits mechanical facts only; the orchestrator decides next action.
    if args.branch:
        reported_files = extract_changed_files(text)
        match, undeclared = diff_vs_report(
            reported_files, args.branch, repo_root=Path(__file__).resolve().parents[1]
        )
        print(f"diff_files_match={int(match)}")
        if undeclared:
            print(f"undeclared_files={','.join(undeclared)}")
        # Undeclared files in the diff are a hard failure for the forbidden-file check:
        # a worker touching .env without declaring it must not pass.
        if not match:
            undeclared_forbidden = [
                f for f in undeclared if any(pat in f for pat in FORBIDDEN_PATTERNS)
            ]
            if undeclared_forbidden:
                forbidden = list(set(forbidden) | set(undeclared_forbidden))
                print(f"forbidden_files_touched={len(forbidden)}")
                print(f"forbidden_files={','.join(forbidden)}")
                checks_passed = False

    # Strict mode: structural Pydantic validation is an extra mechanical fact.
    if os.getenv("KIRO_STRICT_REPORT") == "1":
        schema_valid = required_present  # structural presence is the best we get from Markdown
        print(f"schema_valid={int(schema_valid)}")
        checks_passed = checks_passed and schema_valid

    print(f"mechanical_checks_passed={int(checks_passed)}")

    if args.close_window:
        close_window(args.close_window)
        print(f"close_window={args.close_window}")

    # Exit 0 whenever facts were emitted for an existing report. The orchestrator
    # — not this script — decides accept / needs_fix / PR / merge.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
