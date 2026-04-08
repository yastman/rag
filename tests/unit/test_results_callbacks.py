"""Unit tests for stale legacy results callbacks (#654)."""

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


def _make_callback(data: str = "results:more", user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    return state


def _make_results(n: int = 8) -> list[dict]:
    return [{"id": f"prop-{i}", "payload": {"complex_name": f"Complex {i}"}} for i in range(n)]


@pytest.mark.asyncio
async def test_results_more_is_stale_compat_only() -> None:
    bot = _create_bot()
    bot._send_property_card = AsyncMock()
    state = _make_state({"apartment_results": _make_results(8), "apartment_offset": 0})
    callback = _make_callback("results:more")

    await bot.handle_results_callback(callback, state)

    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
    bot._send_property_card.assert_not_awaited()
    state.update_data.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_results_refine_is_stale_compat_only() -> None:
    bot = _create_bot()
    state = _make_state({"apartment_results": _make_results(3)})
    callback = _make_callback("results:refine")

    await bot.handle_results_callback(callback, state)

    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
    state.update_data.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_results_viewing_is_stale_compat_only() -> None:
    bot = _create_bot()
    state = _make_state({"apartment_results": _make_results(3)})
    callback = _make_callback("results:viewing")
    dialog_manager = AsyncMock()

    await bot.handle_results_callback(callback, state, dialog_manager=dialog_manager)

    dialog_manager.start.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        "Это устаревшая кнопка. Используйте актуальное меню ниже."
    )
    callback.answer.assert_awaited_once_with()
