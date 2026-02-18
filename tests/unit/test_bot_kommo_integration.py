"""Tests for Kommo CRM bot integration (#389).

Verifies that PropertyBot initializes Kommo client when enabled
and injects CRM tools for manager users.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _make_config(**overrides):
    defaults = {
        "telegram_token": "test-token",
        "llm_api_key": "test-key",
    }
    defaults.update(overrides)
    return BotConfig(**defaults)


def test_kommo_client_none_when_disabled():
    """PropertyBot should not init Kommo client when kommo_enabled=False."""
    config = _make_config(kommo_enabled=False)
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.bot.Dispatcher"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
    ):
        bot = PropertyBot(config)

    assert bot._kommo_client is None


def test_kommo_client_set_when_enabled():
    """PropertyBot should init Kommo client when kommo_enabled=True."""
    config = _make_config(
        kommo_enabled=True,
        kommo_subdomain="demo",
        kommo_client_id="cid",
        kommo_client_secret="csecret",
    )
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.bot.Dispatcher"),
        patch("telegram_bot.integrations.cache.CacheLayerManager") as cache_cls,
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
    ):
        cache_cls.return_value = MagicMock()
        cache_cls.return_value.redis = AsyncMock()
        bot = PropertyBot(config)

    assert bot._kommo_client is not None


def test_is_manager_returns_true_for_manager_ids():
    """_is_manager should return True for IDs in manager_ids list."""
    config = _make_config(manager_ids=[111, 222])
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.bot.Dispatcher"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
    ):
        bot = PropertyBot(config)

    assert bot._is_manager(111) is True
    assert bot._is_manager(999) is False
