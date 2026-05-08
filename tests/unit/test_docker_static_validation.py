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
    "mini_app/frontend/Dockerfile",
]

# Images that import telegram_bot.observability (which imports langfuse) must not
# use Python 3.14 because langfuse SDK exercises Pydantic v1 compatibility code
# that is incompatible with Python 3.14.
_LANGFUSE_RUNTIME_DOCKERFILES = [
    "telegram_bot/Dockerfile",
    "mini_app/Dockerfile",
    "src/api/Dockerfile",
    "Dockerfile.ingestion",
]

COMPOSE_CI_ENV = Path("tests/fixtures/compose.ci.env")
MINI_APP_FRONTEND_DOCKERFILE = Path("mini_app/frontend/Dockerfile")
MINI_APP_FRONTEND_NGINX_CONF = Path("mini_app/frontend/nginx.conf")


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


@pytest.mark.parametrize("dockerfile", _LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_dockerfile_does_not_use_python314(dockerfile: str) -> None:
    """Langfuse SDK uses Pydantic v1 compatibility that crashes under Python 3.14.

    Regression test for #1307: bot and mini-app-api containers fail to start
    because `from langfuse import Langfuse` raises
    `pydantic.v1.errors.ConfigError` on Python 3.14.
    """
    text = Path(dockerfile).read_text()
    assert "python3.14" not in text, (
        f"{dockerfile} uses Python 3.14 runtime which is incompatible with langfuse SDK"
    )
    assert "python:3.14" not in text, (
        f"{dockerfile} uses Python 3.14 runtime which is incompatible with langfuse SDK"
    )


@pytest.mark.parametrize("dockerfile", _LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_dockerfile_uses_python313(dockerfile: str) -> None:
    """Langfuse-importing app images must use Python 3.13 runtime (#1346-#1348).

    Docker runtime is pinned to 3.13 while repo native dev may still use
    a local uv environment with a different Python version.
    """
    text = Path(dockerfile).read_text()
    assert "python3.13" in text or "python:3.13" in text, (
        f"{dockerfile} must use Python 3.13 runtime for langfuse SDK compatibility"
    )


def test_mini_app_frontend_dockerfile_runs_as_unprivileged_nginx_user() -> None:
    text = MINI_APP_FRONTEND_DOCKERFILE.read_text()
    assert "USER 101:101" in text, (
        "mini_app/frontend/Dockerfile must run nginx as uid/gid 101 to avoid root-only startup paths"
    )
    assert "COPY nginx.conf /etc/nginx/nginx.conf" in text, (
        "mini_app/frontend/Dockerfile must install the hardened main nginx.conf"
    )
    assert "mkdir -p /tmp/nginx" not in text and "/tmp/nginx/client_temp" not in text, (
        "mini_app/frontend/Dockerfile must not pre-create legacy /tmp/nginx temp directories"
    )


def test_mini_app_frontend_nginx_runtime_paths_use_tmp() -> None:
    text = MINI_APP_FRONTEND_NGINX_CONF.read_text()
    assert "pid /tmp/nginx.pid;" in text
    assert "client_body_temp_path /tmp/client_temp;" in text
    assert "proxy_temp_path /tmp/proxy_temp;" in text
