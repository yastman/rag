#!/usr/bin/env python3
"""CVE gate: run pip-audit (OSV), filter critical/high, enforce allow-list.

Exits non-zero when:
- No packages were scanned (empty scan = false all-clear bug)
- Unfixed critical/high CVEs found outside the allow-list

Usage:
    python scripts/ci/cve_gate.py [--allow VULN_ID ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
import urllib.error
import urllib.request
from typing import Any


# IDs accepted as known false positives or accepted risk.
# Format: CVE-YYYY-NNNNN or GHSA-xxxx-xxxx-xxxx
DEFAULT_ALLOW_LIST: list[str] = []

SEVERITY_BLOCK = {"CRITICAL", "HIGH"}


def osv_severity(ghsa_id: str) -> str | None:
    """Return database_specific.severity from OSV API, or None on failure."""
    url = f"https://api.osv.dev/v1/vulns/{ghsa_id}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # nosec B310 - URL is a hardcoded https constant
            data: dict[str, object] = json.loads(r.read())
            db_specific = data.get("database_specific")
            if isinstance(db_specific, dict):
                sev = db_specific.get("severity")
                return str(sev) if sev is not None else None
            return None
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def get_severity(vuln: dict) -> str:
    """Return severity string for a vuln dict (checks GHSA aliases via OSV)."""
    for alias in vuln.get("aliases", []):
        if alias.startswith("GHSA-"):
            sev = osv_severity(alias)
            if sev:
                return sev.upper()
    return "UNKNOWN"


def run_pip_audit() -> Any:
    """Run pip-audit with OSV service and return parsed JSON."""
    result = subprocess.run(  # nosec B603 B607 - fixed uvx command, no user input
        ["uvx", "pip-audit", "-f", "json", "-s", "osv", "--progress-spinner", "off", "."],
        capture_output=True,
        text=True,
    )
    # pip-audit exits 1 when vulnerabilities are found; that's expected
    if not result.stdout.strip():
        print(f"pip-audit produced no output.\nstderr: {result.stderr}", file=sys.stderr)
        sys.exit(2)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Severity-filtered CVE gate")
    parser.add_argument(
        "--allow",
        metavar="ID",
        action="append",
        default=[],
        help="Allow-list a CVE/GHSA ID (may be repeated)",
    )
    args = parser.parse_args()
    allow_set = set(DEFAULT_ALLOW_LIST) | set(args.allow)

    data = run_pip_audit()
    deps = data.get("dependencies", [])

    # Empty scan = false all-clear bug: fail hard
    if not deps:
        print(
            "ERROR: pip-audit scanned 0 packages — empty scan is not a clean bill of health.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Scanned {len(deps)} packages via OSV.")

    blocking: list[tuple[str, str, str, str]] = []  # (pkg, id, severity, fix)
    for dep in deps:
        for vuln in dep.get("vulns", []):
            vid = vuln["id"]
            all_ids = {vid} | set(vuln.get("aliases", []))
            if all_ids & allow_set:
                continue
            severity = get_severity(vuln)
            if severity in SEVERITY_BLOCK:
                fix = ", ".join(vuln.get("fix_versions", [])) or "none"
                blocking.append((dep["name"], vid, severity, fix))

    if blocking:
        print("\nBlocking CVEs (critical/high, not in allow-list):")
        for pkg, vid, sev, fix in blocking:
            print(f"  {pkg} {vid} [{sev}] fix={fix}")
        print(
            "\nTo accept a known false positive, add --allow <ID> or add to DEFAULT_ALLOW_LIST.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("No blocking CVEs found.")


if __name__ == "__main__":
    main()
