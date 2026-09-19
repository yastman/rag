# tests/unit/ingestion/test_unified_config.py
"""Unified ingestion manifest and physical collection configuration behavior."""

from pathlib import Path

import pytest

from src.ingestion.unified.config import UnifiedConfig
from telegram_bot.config import BotConfig


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


_COLLECTION_INPUTS = (
    "QDRANT_COLLECTION",
    "COLLECTION_NAME",
    "UNIFIED_COLLECTION_NAME",
    "GDRIVE_COLLECTION_NAME",
)


@pytest.fixture
def collection_environment(monkeypatch):
    for name in (*_COLLECTION_INPUTS, "QDRANT_QUANTIZATION_MODE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize(
    "mode,expected",
    [("off", "isolated"), ("scalar", "isolated_scalar"), ("binary", "isolated_binary")],
)
def test_canonical_collection_matches_bot_physical_target(collection_environment, mode, expected):
    collection_environment.setenv("QDRANT_COLLECTION", "isolated")
    collection_environment.setenv("QDRANT_QUANTIZATION_MODE", mode)
    bot = BotConfig(telegram_token="", llm_api_key="test-key", _env_file=None)
    assert UnifiedConfig().collection_name == bot.get_collection_name() == expected


def test_collection_default_matches_bot(collection_environment):
    bot = BotConfig(telegram_token="", llm_api_key="test-key", _env_file=None)
    assert UnifiedConfig().collection_name == bot.get_collection_name() == "gdrive_documents_bge"


@pytest.mark.parametrize("alias", _COLLECTION_INPUTS[1:])
def test_legacy_collection_fallback_is_diagnosed(collection_environment, caplog, alias):
    collection_environment.setenv(alias, "legacy")
    assert UnifiedConfig().collection_name == "legacy"
    assert alias in caplog.text and "QDRANT_COLLECTION" in caplog.text


def test_canonical_collection_wins_over_conflicting_aliases(collection_environment):
    for name, value in zip(
        _COLLECTION_INPUTS, ("canonical", "first", "second", "third"), strict=True
    ):
        collection_environment.setenv(name, value)
    assert UnifiedConfig().collection_name == "canonical"


def test_conflicting_legacy_collections_fail_actionably(collection_environment):
    collection_environment.setenv("COLLECTION_NAME", "first")
    collection_environment.setenv("UNIFIED_COLLECTION_NAME", "second")
    with pytest.raises(ValueError, match="QDRANT_COLLECTION"):
        UnifiedConfig()
    assert UnifiedConfig(collection_name="explicit").collection_name == "explicit"


def test_equal_legacy_aliases_follow_documented_order(collection_environment, caplog):
    for name in _COLLECTION_INPUTS[1:]:
        collection_environment.setenv(name, "same")
    assert UnifiedConfig().collection_name == "same"
    assert "ingestion-only COLLECTION_NAME;" in caplog.text


@pytest.mark.parametrize(
    "mode,expected",
    [("off", "isolated"), ("scalar", "isolated_scalar"), ("binary", "isolated_binary")],
)
def test_existing_suffix_uses_canonical_policy(collection_environment, mode, expected):
    collection_environment.setenv("QDRANT_COLLECTION", "isolated_binary")
    collection_environment.setenv("QDRANT_QUANTIZATION_MODE", mode)
    assert UnifiedConfig().collection_name == expected


async def test_bootstrap_uses_resolved_physical_collection(collection_environment, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from src.ingestion.unified.commands import cmd_bootstrap

    collection_environment.setenv("QDRANT_COLLECTION", "isolated")
    collection_environment.setenv("QDRANT_QUANTIZATION_MODE", "scalar")
    client = MagicMock()
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **_kwargs: client)
    assert await cmd_bootstrap(SimpleNamespace(require_colbert=False)) == 0
    client.get_collection.assert_called_once_with("isolated_scalar")
    client.create_collection.assert_not_called()
