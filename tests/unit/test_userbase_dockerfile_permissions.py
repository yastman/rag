"""Regression tests for USER2-base Dockerfile filesystem permissions."""

from pathlib import Path


def test_user_base_dockerfile_precreates_model_cache_dirs_for_appuser() -> None:
    text = Path("services/user-base/Dockerfile").read_text(encoding="utf-8")
    assert "mkdir -p /models/hf /models/sentence-transformers" in text, (
        "services/user-base/Dockerfile must pre-create model cache directories so mounted "
        "volumes are initialized with writable paths."
    )
    assert "chown -R appuser:appgroup /models" in text, (
        "services/user-base/Dockerfile must hand ownership of /models to appuser."
    )
