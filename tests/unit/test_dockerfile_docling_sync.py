"""Regression tests for Docling service Dockerfile."""

from pathlib import Path


def test_docling_dockerfile_uses_uv_sync_with_lockfile() -> None:
    text = Path("services/docling/Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --no-install-project --extra docling" in text, (
        "services/docling/Dockerfile must use lockfile-backed uv sync with docling extra"
    )


def test_docling_dockerfile_copies_lockfile_artifacts() -> None:
    text = Path("services/docling/Dockerfile").read_text(encoding="utf-8")
    assert "pyproject.toml" in text, (
        "services/docling/Dockerfile must copy pyproject.toml for uv sync"
    )
    assert "uv.lock" in text, (
        "services/docling/Dockerfile must copy uv.lock for reproducible builds"
    )


def test_docling_dockerfile_has_dockerignore() -> None:
    assert Path("services/docling/.dockerignore").exists(), (
        "services/docling/.dockerignore must exist"
    )
