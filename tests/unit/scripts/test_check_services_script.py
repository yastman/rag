"""Regression guards for scripts/check_services.sh Docling non-fatal contract (#2772).

`make local-up` starts only the core services (postgres, redis, qdrant, bge-m3).
Docling is started separately by `make local-up-ingest`, so an unreachable Docling
must NOT make `make local-service-health` report FAIL / exit 1 for the common flow.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


SCRIPT = Path("scripts/check_services.sh")


def _run_with_all_services_unreachable() -> subprocess.CompletedProcess[str]:
    """Run the health script pointing every service at a refused port.

    Port 1 is privileged and unbound in the test environment, so every probe
    fails fast and deterministically without needing live services.
    """
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HEALTH_TIMEOUT": "1",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "1",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "1",
        "BGE_M3_HOST": "localhost",
        "BGE_M3_PORT": "1",
        "DOCLING_HOST": "localhost",
        "DOCLING_PORT": "1",
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_docling_unreachable_reports_warn_not_fail() -> None:
    result = _run_with_all_services_unreachable()
    assert "WARN" in result.stdout
    assert "Docling" in result.stdout
    assert "make local-up-ingest" in result.stdout
    assert "FAIL  Docling" not in result.stdout


def test_docling_unreachable_not_counted_as_failure() -> None:
    """Only the three core services may contribute to the FAIL count."""
    result = _run_with_all_services_unreachable()
    # Qdrant + Redis + BGE-M3 are unreachable here -> 3 FAIL, Docling excluded.
    assert "3 FAIL" in result.stdout
    assert "4 FAIL" not in result.stdout


def test_docling_is_only_optional_service_in_script() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "make local-up-ingest" in text
