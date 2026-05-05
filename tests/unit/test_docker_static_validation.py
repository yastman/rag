"""Static Docker/Compose validation tests (#1243).

These tests validate Docker/Compose configuration without starting live services.
Docker availability is checked at runtime; tests skip gracefully when absent.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


DOCKERFILES = [
    "src/api/Dockerfile",
    "Dockerfile.ingestion",
    "telegram_bot/Dockerfile",
    "services/bge-m3-api/Dockerfile",
    "services/user-base/Dockerfile",
    "services/docling/Dockerfile",
    "src/voice/Dockerfile",
    "mini_app/Dockerfile",
]

COMPOSE_CI_ENV = Path("tests/fixtures/compose.ci.env")


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_dockerfile_exists(dockerfile: str) -> None:
    assert Path(dockerfile).is_file(), f"{dockerfile} not found"


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_compose_dev_config_renders() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(COMPOSE_CI_ENV),
            "-f",
            "compose.yml",
            "-f",
            "compose.dev.yml",
            "config",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Compose dev config failed:\n{result.stderr}"


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_compose_vps_config_renders() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(COMPOSE_CI_ENV),
            "-f",
            "compose.yml",
            "-f",
            "compose.vps.yml",
            "config",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Compose VPS config failed:\n{result.stderr}"


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_compose_dev_config_renders_with_full_profile() -> None:
    """Profile-gated services must not fail merely because required env vars are unset (#1341)."""
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(COMPOSE_CI_ENV),
            "-f",
            "compose.yml",
            "-f",
            "compose.dev.yml",
            "--profile",
            "full",
            "config",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Compose dev config with --profile full failed:\n{result.stderr}"
    )
