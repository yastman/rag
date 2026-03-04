"""Tests for Python ABI consistency in multi-stage Dockerfiles.

Builder and runtime must use the same Python major.minor version,
otherwise binary wheels (asyncpg, uvloop, etc.) will fail at import time.
"""

import re
from pathlib import Path


def _get_builder_python_version(dockerfile_text: str) -> str:
    """Extract Python version from uv builder image tag (e.g. uv:0.9-python3.12-...)."""
    match = re.search(r"astral-sh/uv:[^-]+-python(\d+\.\d+)-", dockerfile_text)
    assert match, "Could not find uv builder image with python version"
    return match.group(1)


def _get_runtime_python_version(dockerfile_text: str) -> str:
    """Extract Python version from runtime FROM line (e.g. FROM python:3.12-slim-bookworm)."""
    match = re.search(r"FROM python:(\d+\.\d+)-slim", dockerfile_text)
    assert match, "Could not find runtime python image with version"
    return match.group(1)


def test_api_dockerfile_python_version_consistency() -> None:
    text = Path("src/api/Dockerfile").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"src/api/Dockerfile: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )


def test_ingestion_dockerfile_python_version_consistency() -> None:
    text = Path("Dockerfile.ingestion").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"Dockerfile.ingestion: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )


def test_telegram_bot_dockerfile_python_version_consistency() -> None:
    text = Path("telegram_bot/Dockerfile").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"telegram_bot/Dockerfile: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )


def test_bge_m3_dockerfile_python_version_consistency() -> None:
    text = Path("services/bge-m3-api/Dockerfile").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"services/bge-m3-api/Dockerfile: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )


def test_user_base_dockerfile_python_version_consistency() -> None:
    text = Path("services/user-base/Dockerfile").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"services/user-base/Dockerfile: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )


def test_docling_dockerfile_python_version_consistency() -> None:
    text = Path("services/docling/Dockerfile").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"services/docling/Dockerfile: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )


def test_voice_dockerfile_python_version_consistency() -> None:
    text = Path("src/voice/Dockerfile").read_text(encoding="utf-8")
    builder_ver = _get_builder_python_version(text)
    runtime_ver = _get_runtime_python_version(text)
    assert builder_ver == runtime_ver, (
        f"src/voice/Dockerfile: builder Python {builder_ver} != runtime Python {runtime_ver}. "
        "Binary wheels compiled for one version break on another."
    )
