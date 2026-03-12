"""Tests for card:ask including format_card_context in prompt_text (#937)."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_callback(data: str, user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    return state


def _sample_result(property_id: str = "prop-42") -> dict:
    return {
        "id": property_id,
        "score": 0.95,
        "payload": {
            "complex_name": "Ocean Vista",
            "property_type": "1-спальня",
            "price_eur": 250000,
            "apartment_number": "305",
        },
    }


async def test_card_ask_passes_apartment_context_in_prompt() -> None:
    """card:ask with matched apartment passes format_card_context in prompt_text."""
    bot = _create_bot()
    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("card:ask:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock) as mock_spc:
        await bot.handle_card_callback(callback, state)

        mock_spc.assert_awaited_once()
        call_kwargs = mock_spc.call_args.kwargs
        prompt = call_kwargs.get("prompt_text", "")
        assert prompt, "prompt_text must be non-empty when apartment is matched"
        assert "Ocean Vista" in prompt
        assert "250 000" in prompt


async def test_card_ask_swaps_keyboard() -> None:
    """card:ask edits the card message to remove inline buttons (keyboard swap)."""
    bot = _create_bot()
    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("card:ask:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock):
        await bot.handle_card_callback(callback, state)

    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
