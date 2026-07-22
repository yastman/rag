"""Regression guards for scripts/check_services.sh Ingestion contract.

`make local-up` starts only the core services (postgres, redis, qdrant, bge-m3).
Ingestion is started by `make local-up-ingest`, and its health is verified
via `docker compose ps` on the actual Compose `ingestion` container.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


SCRIPT = Path("scripts/check_services.sh")

# Locate a bash that produces clean UTF-8 output on all platforms.
# On Windows, WSL System32 bash.exe outputs UTF-16LE to pipes, so we
# prefer Git Bash when available. On Linux/macOS, plain "bash" works.
_BASH: str | None = None
for _candidate in (
    # Git Bash paths first — on Windows they beat the WSL System32 shim
    # which outputs UTF-16LE to pipes, breaking text capture.
    "C:\\Program Files\\Git\\bin\\bash.exe",
    "C:\\Program Files\\Git\\usr\\bin\\bash.exe",
    shutil.which("bash"),
):
    if _candidate and os.path.exists(_candidate):
        _BASH = _candidate
        break
assert _BASH is not None, "no bash executable found on PATH"


def _run_with_all_services_unreachable() -> subprocess.CompletedProcess[str]:
    """Run the health script pointing every core service at a refused port.

    Port 1 is privileged and unbound in the test environment, so every probe
    fails fast and deterministically without needing live services.
    The ingestion check (docker compose ps) will be skipped since docker
    is unavailable under the restricted PATH — this avoids needing Docker.
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
    }
    return subprocess.run(
        [_BASH, str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def test_no_docling_health_probe_remains() -> None:
    """Docling HTTP health probe and its helper have been removed."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DOCLING_" not in text
    assert "Docling" not in text
    assert "check_http_optional" not in text


def test_ingestion_health_check_present() -> None:
    """Script contains a Compose-based ingestion health check targeting the actual container."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "check_ingestion" in text
    assert "docker compose" in text
    assert "compose.yml" in text
    assert "compose.dev.yml" in text
    assert "--profile ingest" in text
    assert "ingestion" in text
    assert "healthy" in text


def test_all_core_services_unreachable_reports_3_fail() -> None:
    """Only the three core services (Qdrant, Redis, BGE-M3) contribute to the FAIL count."""
    result = _run_with_all_services_unreachable()
    # Core services all fail (port 1) -> 3 FAIL. Ingestion is SKIPped (no Docker).
    assert "3 FAIL" in result.stdout
    assert "SKIP  Ingestion" in result.stdout


def test_ingestion_skipped_when_docker_unavailable() -> None:
    """Ingestion check gracefully skips when docker is not on PATH."""
    result = _run_with_all_services_unreachable()
    assert "SKIP  Ingestion  (docker not available)" in result.stdout


def test_up_unhealthy_does_not_match_pass_pattern() -> None:
    """The healthy-status grep pattern rejects 'Up ... (unhealthy)'."""
    result = subprocess.run(
        [
            _BASH,
            "-c",
            r"""echo 'Up 2 minutes (unhealthy)' | grep -qE '^Up[[:space:]].*\(healthy\)'""",
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0, f"expected non-zero (no match), got {result.returncode}"


def test_up_starting_does_not_match_pass_pattern() -> None:
    """The healthy-status grep pattern rejects 'Up ... (starting)'."""
    result = subprocess.run(
        [
            _BASH,
            "-c",
            r"""echo 'Up 5 seconds (starting)' | grep -qE '^Up[[:space:]].*\(healthy\)'""",
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0, f"expected non-zero (no match), got {result.returncode}"


def test_env_file_arg_parsed() -> None:
    """Script accepts --env-file CLI argument with .env / fixture fallback."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--env-file" in text, "script must accept --env-file"
    assert "ENV_FILE" in text, "ENV_FILE variable must exist"


def test_project_name_arg_parsed() -> None:
    """Script accepts --project-name CLI argument for Compose project override."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--project-name" in text, "script must accept --project-name"


def test_env_file_default_fallback_to_fixture() -> None:
    """Default env-file falls back to fixture when .env absent (mirrors Makefile)."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "tests/fixtures/compose.ci.env" in text, "fixture fallback must be present"


def test_bash_candidates_ordered_git_bash_first() -> None:
    """Bash candidate list prefers known Git Bash paths over shutil.which (WSL shim)."""
    text = Path(__file__).read_text(encoding="utf-8")
    git_bash_first = text.find("Program Files\\\\Git")
    which_bash = text.find("shutil.which")
    assert git_bash_first != -1, "Git Bash path must be in candidate list"
    assert which_bash != -1, "shutil.which must be in candidate list"
    assert git_bash_first < which_bash, "Git Bash paths must precede shutil.which fallback"
