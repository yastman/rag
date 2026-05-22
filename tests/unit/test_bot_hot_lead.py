"""Test HotLeadNotifier wiring in PropertyBot (#402)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        telegram_token="test-token",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        manager_ids=[123],
        manager_hot_lead_threshold=60,
        manager_hot_lead_dedupe_sec=3600,
    )


def _create_bot(config: BotConfig):
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

        return PropertyBot(config)


class TestHotLeadNotifierWiring:
    """Verify HotLeadNotifier attribute exists on PropertyBot."""

    def test_bot_has_notifier_attribute(self):
        """PropertyBot must declare _hot_lead_notifier attribute."""
        bot = _create_bot(_make_config())
        assert hasattr(bot, "_hot_lead_notifier")
        assert bot._hot_lead_notifier is None  # not yet initialized

    def test_notifier_importable_and_has_interface(self):
        """HotLeadNotifier is importable and has notify_if_hot method."""
        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        assert hasattr(HotLeadNotifier, "notify_if_hot")
        assert callable(getattr(HotLeadNotifier, "notify_if_hot", None))
