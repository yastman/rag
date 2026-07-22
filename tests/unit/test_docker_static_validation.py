"""Static Docker/Compose validation tests (#1243).

These tests validate Docker/Compose configuration without starting live services.
Docker availability is checked at runtime; tests skip gracefully when absent.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from aiogram.utils.token import validate_token


DOCKERFILES = [
    "Dockerfile.ingestion",
    "telegram_bot/Dockerfile",
    "services/bge-m3-api/Dockerfile",
]

# Images that import telegram_bot.observability (which imports langfuse) must not
# use Python 3.14 because langfuse SDK exercises Pydantic v1 compatibility code
# that is incompatible with Python 3.14.
_LANGFUSE_RUNTIME_DOCKERFILES = [
    "telegram_bot/Dockerfile",
    "Dockerfile.ingestion",
]

COMPOSE_CI_ENV = Path("tests/fixtures/compose.ci.env")
COMPOSE_FILE = Path("compose.yml")
ENV_EXAMPLE = Path(".env.example")
QDRANT_STACK_DOC = Path("docs/QDRANT_STACK.md")


def _docker_available() -> bool:
    """Return True only when both ``docker`` and the Compose v2 plugin are usable.

    On hosts that ship the engine without the Compose plugin
    (lightweight CI sandboxes, default Amazon Linux 2023, etc.)
    ``shutil.which("docker")`` returns truthy but ``docker compose ...``
    exits 125 ("looking up compose provider failed"). Probing the plugin
    here lets the static-validation tests skip gracefully instead of
    asserting on the plugin error message. Tracked under #2009.
    """
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _run_docker_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    if not _docker_available():
        pytest.skip("Docker / Compose plugin not available")
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("Docker / Compose plugin not available")
    # Defensive: if the Compose plugin disappeared between the probe and
    # this call (or the host emits the same "compose provider failed"
    # error from a different path), downgrade to skip so we never flip a
    # missing-runtime condition into a hard FAIL.
    if result.returncode == 125 and "compose provider failed" in (result.stderr or ""):
        pytest.skip("Docker Compose plugin missing at runtime")
    return result


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


def test_compose_ci_telegram_token_is_sdk_valid() -> None:
    """Fallback env must let `make bot` reach runtime startup, not fail token parsing."""
    values = dict(
        line.split("=", 1)
        for line in COMPOSE_CI_ENV.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    validate_token(values["TELEGRAM_BOT_TOKEN"])


def test_compose_dev_postgres_renders_with_dev_only_capabilities() -> None:
    """Dev Postgres keeps base cap_drop while adding only startup capabilities."""
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
            "postgres",
        ],
    )
    assert result.returncode == 0, f"Compose postgres config failed:\n{result.stderr}"

    import yaml

    rendered = yaml.safe_load(result.stdout)
    postgres = rendered["services"]["postgres"]
    assert postgres["cap_drop"] == ["ALL"]
    assert set(postgres["cap_add"]) == {
        "CHOWN",
        "FOWNER",
        "DAC_OVERRIDE",
        "SETGID",
        "SETUID",
    }


@pytest.mark.parametrize("dockerfile", _LANGFUSE_RUNTIME_DOCKERFILES)
def test_langfuse_dockerfile_does_not_use_python314(dockerfile: str) -> None:
    """Langfuse SDK uses Pydantic v1 compatibility that crashes under Python 3.14.

    Regression test for #1307: bot containers fail to start
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


# ── BGE-M3 ONNX runtime packaging gate (PR #2229) ──────────────────────────

_CI_ENV_KEYS: frozenset[str] | None = None


def _ci_env_map() -> dict[str, str]:
    """Parse key/value pairs from the deterministic Compose CI env fixture."""
    return dict(
        line.split("=", 1)
        for line in COMPOSE_CI_ENV.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def _ci_env_keys() -> frozenset[str]:
    """Lazily parsed set of env var keys from the CI env fixture."""
    global _CI_ENV_KEYS
    if _CI_ENV_KEYS is None:
        _CI_ENV_KEYS = frozenset(_ci_env_map())
    return _CI_ENV_KEYS


def test_bge_m3_build_uses_onnx_model_context() -> None:
    """bge-m3 must bake ONNX INT8 artifacts into the image at build time (#2229)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    bge_m3 = compose["services"]["bge-m3"]
    build = bge_m3["build"]
    assert build["additional_contexts"]["bge_m3_onnx_model"].startswith(
        "${BGE_M3_ONNX_MODEL_HOST_DIR:"
    ), (
        "bge-m3 build must use BGE_M3_ONNX_MODEL_HOST_DIR as a named build "
        "context for ONNX INT8 artifacts"
    )


def test_bge_m3_has_hf_subdirectory_mount() -> None:
    """bge-m3 should mount a narrower HF-only subdirectory (e.g. /models/hf)
    so the ONNX path ``/models/onnx`` remains usable (#2229)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    bge_m3 = compose["services"]["bge-m3"]
    volumes = bge_m3.get("volumes", [])
    targets: set[str] = set()
    for vol in volumes:
        target = vol.split(":")[1].split("@")[0] if isinstance(vol, str) else vol.get("target", "")
        targets.add(target)
    assert "/models/hf" in targets, (
        "bge-m3 needs a narrow HF cache mount at /models/hf so "
        "/models/onnx for ONNX artifacts is not masked"
    )
    assert "/models/onnx" not in targets, (
        "bge-m3 must not mount /models/onnx at runtime; the INT8 model is "
        "baked into the Docker image during build"
    )


def test_bge_m3_model_cache_dir_uses_writable_hf_cache() -> None:
    """The tokenizer cache must use the HF volume, not /models root (#2229)."""
    import yaml

    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    bge_m3 = compose["services"]["bge-m3"]
    environment = bge_m3["environment"]
    assert environment["MODEL_CACHE_DIR"] == "/models/hf"
    assert environment["HF_HOME"] == "/models/hf"
    assert environment["TRANSFORMERS_CACHE"] == "/models/hf"


def test_bge_m3_dockerfile_prepares_model_dirs_for_appuser() -> None:
    """Named volumes inherit target ownership on first use; prepare /models."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text()
    assert "mkdir -p /models/hf /models/onnx" in dockerfile
    assert "chown -R appuser:appgroup /models" in dockerfile


def test_bge_m3_dockerfile_bakes_int8_model_from_build_context() -> None:
    """The Docker image must contain the ONNX INT8 artifacts, not require a runtime mount."""
    dockerfile = Path("services/bge-m3-api/Dockerfile").read_text()
    assert "from=bge_m3_onnx_model" in dockerfile
    assert "model.int8.onnx" in dockerfile
    assert "model.int8.onnx.data" in dockerfile
    assert "cp /tmp/bge-m3-onnx/model.int8.onnx" in dockerfile


def test_bge_m3_onnx_model_dir_env_in_ci_env() -> None:
    """tests/fixtures/compose.ci.env must define BGE_M3_ONNX_MODEL_HOST_DIR so
    Compose config rendering can resolve the bind-mount source (#2229)."""
    ci_env = _ci_env_map()
    assert "BGE_M3_ONNX_MODEL_HOST_DIR" in ci_env, (
        "BGE_M3_ONNX_MODEL_HOST_DIR is missing from tests/fixtures/compose.ci.env; "
        "Compose config rendering requires it for the ONNX model bind mount"
    )
    model_dir = Path(ci_env["BGE_M3_ONNX_MODEL_HOST_DIR"])
    assert not model_dir.is_absolute(), (
        "tests/fixtures/compose.ci.env must use a repo-relative ONNX fixture path, "
        f"not a host-specific absolute path: {model_dir}"
    )
    assert (model_dir / "model.int8.onnx").is_file(), (
        "Compose CI BGE model context must include model.int8.onnx so "
        "`docker compose build bge-m3` does not depend on host-local artifacts"
    )
    assert (model_dir / "model.int8.onnx.data").is_file(), (
        "Compose CI BGE model context must include model.int8.onnx.data so "
        "`docker compose build bge-m3` does not depend on host-local artifacts"
    )


def test_bge_m3_onnx_model_dir_env_in_env_example() -> None:
    """.env.example must document BGE_M3_ONNX_MODEL_HOST_DIR as a local-dev
    path for the ONNX INT8 artifact bind mount (#2229)."""
    text = ENV_EXAMPLE.read_text()
    assert "BGE_M3_ONNX_MODEL_HOST_DIR" in text, (
        "BGE_M3_ONNX_MODEL_HOST_DIR must be documented in .env.example "
        "for local ONNX model provisioning"
    )
    assert "/home/user/" not in text, (
        ".env.example must not hardcode developer-local absolute paths"
    )


def test_compose_ci_langfuse_env_has_bge_m3_inputs() -> None:
    """CI compose env must provide the local Langfuse inputs bge-m3 consumes."""
    keys = _ci_env_keys()
    assert "LANGFUSE_PUBLIC_KEY" in keys
    assert "LANGFUSE_SECRET_KEY" in keys
    assert "LANGFUSE_DOCKER_HOST" in keys


def test_compose_dev_bge_m3_renders_with_ci_env() -> None:
    """Compose dev config rendering must succeed for ``bge-m3`` with the CI env fixture."""
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
            "bge-m3",
        ],
    )
    assert result.returncode == 0, (
        f"Compose bge-m3 config rendering failed:\n{result.stderr or result.stdout}"
    )
