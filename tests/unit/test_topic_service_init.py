"""Verify TopicService is initialized on bot startup."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_bot_has_topic_service_attr(monkeypatch):
    """PropertyBot should have _topic_service after init."""
    monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
    monkeypatch.delenv("KOMMO_ACCESS_TOKEN", raising=False)

    from telegram_bot.config import BotConfig

    config = BotConfig(
        _env_file=None,
        telegram_token="123456789:AABBCCDDEEFFaabbccddeeff-1234567890",
        llm_api_key="test",
        voyage_api_key="test",
    )

    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot(config)
        assert hasattr(bot, "_topic_service")
        assert bot._topic_service is None  # Initialized in start()
