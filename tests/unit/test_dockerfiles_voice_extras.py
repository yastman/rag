"""Regression tests for Dockerfiles that run API/voice services."""

from pathlib import Path


def test_api_dockerfile_installs_voice_extra_dependencies() -> None:
    text = Path("src/api/Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --extra voice --no-install-project" in text
    assert "uv sync --frozen --no-dev --extra voice" in text


def test_voice_dockerfile_installs_voice_extra_dependencies() -> None:
    text = Path("src/voice/Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --extra voice --no-install-project" in text
    assert "uv sync --frozen --no-dev --extra voice" in text


def test_api_dockerfile_sets_python_unbuffered() -> None:
    text = Path("src/api/Dockerfile").read_text(encoding="utf-8")
    assert "PYTHONUNBUFFERED=1" in text, "src/api/Dockerfile runtime must set PYTHONUNBUFFERED=1"


def test_voice_dockerfile_sets_python_unbuffered() -> None:
    text = Path("src/voice/Dockerfile").read_text(encoding="utf-8")
    assert "PYTHONUNBUFFERED=1" in text, "src/voice/Dockerfile runtime must set PYTHONUNBUFFERED=1"
