"""Unit tests for scripts/ci/cve_gate.py severity/empty-scan logic.

Covers the four exit-code branches of ``main()`` without invoking pip-audit or
the OSV network API:

* empty scan (0 packages)        -> SystemExit(2)  (false all-clear guard)
* unfixed CRITICAL/HIGH CVE      -> SystemExit(1)
* allow-listed CVE ID            -> exit 0 (skipped before severity lookup)
* UNKNOWN severity (no GHSA)     -> exit 0 (not in SEVERITY_BLOCK)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.ci import cve_gate


def _run_main(scan: dict, argv: list[str] | None = None) -> None:
    """Invoke cve_gate.main() with run_pip_audit() stubbed to return ``scan``."""
    with (
        patch.object(cve_gate, "run_pip_audit", return_value=scan),
        patch.object(cve_gate.sys, "argv", ["cve_gate", *(argv or [])]),
    ):
        cve_gate.main()


def test_empty_deps_exits_2() -> None:
    """Scanning 0 packages is treated as a false all-clear and fails hard."""
    with pytest.raises(SystemExit) as exc:
        _run_main({"dependencies": []})
    assert exc.value.code == 2


def test_critical_vuln_exits_1() -> None:
    """An unfixed CRITICAL/HIGH CVE outside the allow-list blocks (exit 1)."""
    scan = {
        "dependencies": [
            {
                "name": "somepkg",
                "vulns": [
                    {
                        "id": "PYSEC-2024-1",
                        "aliases": ["GHSA-aaaa-bbbb-cccc"],
                        "fix_versions": ["1.2.3"],
                    }
                ],
            }
        ]
    }
    with (
        patch.object(cve_gate, "osv_severity", return_value="CRITICAL"),
        pytest.raises(SystemExit) as exc,
    ):
        _run_main(scan)
    assert exc.value.code == 1


def test_allow_listed_id_passes() -> None:
    """A CVE listed via --allow is skipped before any severity lookup (exit 0)."""
    scan = {
        "dependencies": [
            {
                "name": "somepkg",
                "vulns": [
                    {
                        "id": "PYSEC-2024-1",
                        "aliases": ["GHSA-aaaa-bbbb-cccc"],
                        "fix_versions": ["1.2.3"],
                    }
                ],
            }
        ]
    }
    # osv_severity would raise if called; allow-list must short-circuit first.
    with patch.object(
        cve_gate,
        "osv_severity",
        side_effect=AssertionError("severity looked up despite allow-list"),
    ):
        _run_main(scan, argv=["--allow", "PYSEC-2024-1"])  # returns normally => exit 0


def test_unknown_severity_passes() -> None:
    """A vuln with no resolvable GHSA severity is UNKNOWN and does not block."""
    scan = {
        "dependencies": [
            {
                "name": "somepkg",
                "vulns": [{"id": "PYSEC-2024-2", "aliases": []}],
            }
        ]
    }
    _run_main(scan)  # UNKNOWN not in SEVERITY_BLOCK => returns normally => exit 0
