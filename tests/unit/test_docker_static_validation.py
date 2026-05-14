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
COMPOSE_FILE = Path("compose.yml")
ENV_EXAMPLE = Path(".env.example")
QDRANT_STACK_DOC = Path("docs/QDRANT_STACK.md")


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _run_docker_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    if not _docker_available():
        pytest.skip("Docker not available")
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("Docker not available")


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_dockerfile_exists(dockerfile: str) -> None:
    assert Path(dockerfile).is_file(), f"{dockerfile} not found"


def test_compose_dev_config_renders() -> None:
    result = _run_docker_command(
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
    )
    assert result.returncode == 0, f"Compose dev config failed:\n{result.stderr}"


def test_compose_vps_config_renders() -> None:
    result = _run_docker_command(
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
    )
    assert result.returncode == 0, f"Compose VPS config failed:\n{result.stderr}"


def test_compose_dev_config_renders_with_full_profile() -> None:
    """Profile-gated services must not fail merely because required env vars are unset (#1341)."""
    result = _run_docker_command(
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


def test_voice_agent_healthcheck_does_not_use_rag_api_port() -> None:
    """voice-agent healthcheck must not reference port 8080 to avoid confusion with rag-api (#1510)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    voice = compose["services"]["voice-agent"]
    health_test = " ".join(voice["healthcheck"]["test"])
    assert "8080" not in health_test, (
        "voice-agent healthcheck must not reference port 8080 (rag-api); use a process check instead"
    )


def test_voice_agent_has_otel_service_name() -> None:
    """voice-agent must set a stable OTEL_SERVICE_NAME default like other Langfuse-instrumented services (#1510)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    voice = compose["services"]["voice-agent"]
    env = voice.get("environment", {})
    assert "OTEL_SERVICE_NAME" in env, "voice-agent must set OTEL_SERVICE_NAME in compose.yml"
    assert "voice-agent" in env["OTEL_SERVICE_NAME"], (
        "voice-agent OTEL_SERVICE_NAME default must include 'voice-agent'"
    )


def test_mini_app_api_depends_on_postgres() -> None:
    """mini-app-api uses REALESTATE_DATABASE_URL and must declare a postgres dependency (#1510)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    mini = compose["services"]["mini-app-api"]
    deps = mini.get("depends_on", {})
    assert "postgres" in deps, "mini-app-api must depend_on postgres"


def test_docling_read_only_has_explanatory_comment() -> None:
    """docling overrides read_only: false and must have an explanatory comment like litellm (#1510)."""
    text = COMPOSE_FILE.read_text()
    # Find the docling service block by locating the next service at the same indent
    docling_start = text.find("  docling:")
    assert docling_start != -1, "docling service not found in compose.yml"
    # Services are separated by a blank line followed by "  <service-name>:" at column 0
    next_service = text.find("\n\n  ", docling_start + 1)
    block = text[docling_start : next_service if next_service != -1 else None]
    assert "read_only: false" in block, "docling must set read_only: false"
    # The comment should appear before read_only: false in the same block
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if "read_only: false" in line:
            # Check preceding 2 lines for a comment
            preceding = "\n".join(lines[max(0, i - 2) : i])
            assert "#" in preceding, (
                "docling read_only: false must have an explanatory comment nearby"
            )
            break
    else:
        pytest.fail("read_only: false not found in docling block")


def test_qdrant_stack_doc_matches_compose_version() -> None:
    """docs/QDRANT_STACK.md must reference the same Qdrant version as compose.yml (#1510)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    qdrant_image = compose["services"]["qdrant"]["image"]
    # Extract tag from image string, e.g. qdrant/qdrant:v1.18.0@sha256:...
    tag = qdrant_image.split(":")[1].split("@")[0]

    doc_text = QDRANT_STACK_DOC.read_text()
    assert tag in doc_text, (
        f"docs/QDRANT_STACK.md must reference Qdrant version {tag} (from compose.yml)"
    )


# ── voice-agent healthcheck runtime safety (#1510) ─────────────────────────


def test_voice_agent_compose_healthcheck_is_runtime_safe() -> None:
    """voice-agent compose healthcheck must use Python stdlib available in python:slim."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    voice = compose["services"]["voice-agent"]
    health_test = " ".join(voice["healthcheck"]["test"])
    assert "pgrep" not in health_test, (
        "voice-agent compose healthcheck runs inside python:slim; pgrep requires procps"
    )
    assert "python -c" in health_test, (
        "voice-agent compose healthcheck must use Python stdlib available in the image"
    )
    assert "src.voice.agent" not in health_test, (
        "voice-agent compose healthcheck must not contain the literal process needle; "
        "build it dynamically to avoid self-matching the healthcheck command"
    )
    assert "'src.voice.' + 'agent'" in health_test


def test_voice_dockerfile_healthcheck_does_not_use_localhost_8080() -> None:
    """src/voice/Dockerfile must not reference localhost:8080/health (#1510)."""
    dockerfile = Path("src/voice/Dockerfile").read_text()
    assert "localhost:8080/health" not in dockerfile, (
        "src/voice/Dockerfile healthcheck must not reference localhost:8080 (rag-api endpoint)"
    )
    assert "8080" not in dockerfile, (
        "src/voice/Dockerfile must not reference port 8080 (rag-api port)"
    )


def test_voice_dockerfile_healthcheck_is_self_match_safe() -> None:
    """src/voice/Dockerfile HEALTHCHECK must not contain the process needle literally (#1510)."""
    dockerfile = Path("src/voice/Dockerfile").read_text()
    healthcheck = dockerfile.split("HEALTHCHECK", 1)[1].split("\n\nCMD", 1)[0]
    assert "python -c" in healthcheck, (
        "src/voice/Dockerfile HEALTHCHECK must use Python stdlib in python:slim runtime"
    )
    assert "src.voice.agent" not in healthcheck, (
        "src/voice/Dockerfile HEALTHCHECK must not contain the literal process needle; "
        "build it dynamically to avoid self-matching the healthcheck command"
    )
    assert "'src.voice.' + 'agent'" in healthcheck
