"""Unit tests for PropertyBot._send_property_card DRY helper."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_favorites_callbacks.py)
# ---------------------------------------------------------------------------


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


def _sample_result(property_id: str = "prop-1") -> dict:
    return {
        "id": property_id,
        "score": 0.9,
        "payload": {
            "complex_name": "Test Complex",
            "city": "Бургас",
            "property_type": "Студия",
            "floor": 2,
            "area_m2": 45,
            "view_tags": ["sea"],
            "view_primary": "sea",
            "price_eur": 55000,
        },
    }


# ---------------------------------------------------------------------------
# Tests: _send_property_card
# ---------------------------------------------------------------------------


async def test_send_property_card_calls_format_and_answer() -> None:
    """_send_property_card formats card, checks favorite, sends with 2+1 buttons."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.is_favorited = AsyncMock(return_value=False)

    message = MagicMock()
    message.answer = AsyncMock()

    result = _sample_result("prop-1")

    await bot._send_property_card(message, result, telegram_id=123)

    message.answer.assert_awaited_once()
    call_kwargs = message.answer.call_args
    kb = call_kwargs.kwargs.get("reply_markup") or call_kwargs[1].get("reply_markup")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "card:viewing:prop-1" in callbacks
    assert "fav:add:prop-1" in callbacks
    assert "card:ask:prop-1" in callbacks


async def test_send_property_card_favorited_shows_remove() -> None:
    """If property is favorited, button shows fav:remove."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.is_favorited = AsyncMock(return_value=True)

    message = MagicMock()
    message.answer = AsyncMock()

    result = _sample_result("prop-1")

    await bot._send_property_card(message, result, telegram_id=123)

    kb = message.answer.call_args.kwargs.get("reply_markup")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "fav:remove:prop-1" in callbacks
    assert "fav:add:prop-1" not in callbacks


async def test_send_property_card_no_favorites_service() -> None:
    """If _favorites_service is not set, is_favorited defaults to False (no crash)."""
    bot = _create_bot()
    # Ensure no favorites service
    if hasattr(bot, "_favorites_service"):
        del bot._favorites_service

    message = MagicMock()
    message.answer = AsyncMock()

    result = _sample_result("prop-99")

    await bot._send_property_card(message, result, telegram_id=42)

    message.answer.assert_awaited_once()
    kb = message.answer.call_args.kwargs.get("reply_markup")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "fav:add:prop-99" in callbacks
