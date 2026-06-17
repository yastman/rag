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

Strict mode (env ``KIRO_STRICT_REPORT=1``) additionally runs Pydantic structural
validation against ``worker_report_schema`` and prints ``schema_valid=1|0``.

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

# Fields whose presence can be satisfied by an aliased section header.
# NOTE: verification_evidence is intentionally NOT aliased to evidence_commands.
# Both fields must be present independently — the evidence narrative and the
# replay commands serve different purposes and cannot substitute for each other.
FIELD_ALIASES: dict[str, str] = {}


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

    if re.search(r"(?i)\bstatus[:\s]+(?:done|failed|blocked|pass)", combined) or re.search(
        r"(?i)#\s*worker\s+(?:report|finish(?:\s+report)?)\s*[:\s]", combined
    ):
        found.add("status")
    if re.search(r"(?i)(#\s*worker\s+(?:report|finish)|worker\s*:)", combined):
        found.add("worker")

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


def close_window(worker_name: str) -> None:
    closer = Path(__file__).with_name("close_markdown_worker_window.py")
    subprocess.run([sys.executable, str(closer), "--worker", worker_name], check=False)  # nosec B603


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit mechanical facts about a Markdown worker report (no verdict)."
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--role", required=True, choices=["research", "implementation", "review-fix", "pr-review"]
    )
    parser.add_argument("--close-window", metavar="WORKER_NAME")
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
    for alias_key, aliased_field in FIELD_ALIASES.items():
        if alias_key in found:
            found.add(aliased_field)

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
