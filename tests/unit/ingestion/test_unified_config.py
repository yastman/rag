# tests/unit/ingestion/test_unified_config.py
"""Tests for UnifiedConfig manifest_dir / effective_manifest_dir (#215)."""

from pathlib import Path

from src.ingestion.unified.config import UnifiedConfig


class TestManifestDir:
    """Verify MANIFEST_DIR env var wiring and fallback."""

    def test_effective_manifest_dir_with_env(self, monkeypatch):
        monkeypatch.setenv("MANIFEST_DIR", "/data/manifest")
        config = UnifiedConfig()
        assert config.effective_manifest_dir() == Path("/data/manifest")

    def test_effective_manifest_dir_fallback(self, monkeypatch):
        monkeypatch.delenv("MANIFEST_DIR", raising=False)
        config = UnifiedConfig()
        assert config.effective_manifest_dir() == config.sync_dir

    def test_manifest_dir_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("MANIFEST_DIR", raising=False)
        config = UnifiedConfig()
        assert config.manifest_dir is None
