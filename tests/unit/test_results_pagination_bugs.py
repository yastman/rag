"""Compatibility tests for stale legacy results callbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
        telegram_token="test-token",
        voyage_api_key="voyage-key",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="test_collection",
        redis_url="redis://localhost:6379",
        realestate_database_url="postgresql://postgres:postgres@127.0.0.1:1/realestate",
        rerank_provider="none",
    )


def _create_bot() -> PropertyBot:
    config = _make_config()
    with (
        patch("telegram_bot.bot.Bot"),
        patch("telegram_bot.integrations.cache.CacheLayerManager"),
        patch("telegram_bot.integrations.embeddings.BGEM3HybridEmbeddings"),
        patch("telegram_bot.integrations.embeddings.BGEM3SparseEmbeddings"),
        patch("telegram_bot.services.qdrant.QdrantService"),
        patch("telegram_bot.graph.config.GraphConfig.create_llm"),
        patch("telegram_bot.graph.config.GraphConfig.create_supervisor_llm"),
    ):
        return PropertyBot(config)


def _make_callback() -> MagicMock:
    cb = MagicMock()
    cb.data = "results:more"
    cb.from_user = MagicMock(id=12345)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def _make_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    return state


@pytest.mark.asyncio
async def test_results_more_stale_compat_does_not_call_scroll_with_filters() -> None:
    bot = _create_bot()
    bot._apartments_service = MagicMock()
    bot._apartments_service.scroll_with_filters = AsyncMock()
    state = _make_state(
        {
            "apartment_results": [{"id": "apt-1"}],
            "apartment_offset": 0,
            "apartment_total": 20,
            "apartment_next_offset": 55000.0,
            "apartment_filters": {"rooms": 2},
            "apartment_scroll_seen_ids": ["apt-1"],
        }
    )
    callback = _make_callback()

    await bot.handle_results_callback(callback, state)

    bot._apartments_service.scroll_with_filters.assert_not_awaited()
    state.update_data.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
