"""Unit tests for handle_card_callback (card:viewing, card:ask) #705."""

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


def _make_callback(data: str, user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.answer_media_group = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _sample_result(property_id: str = "prop-42") -> dict:
    return {
        "id": property_id,
        "score": 0.95,
        "payload": {
            "complex_name": "Ocean Vista",
            "city": "Dubai",
            "property_type": "Studio",
            "floor": 5,
            "area_m2": 55,
            "view_tags": ["Sea", "Pool"],
            "view_primary": "Sea",
            "price_eur": 250000,
        },
    }


# ---------------------------------------------------------------------------
# Tests: handle_card_callback
# ---------------------------------------------------------------------------


async def test_card_viewing_starts_phone_collection() -> None:
    """card:viewing:{id} → start_phone_collection with service_key=viewing."""
    bot = _create_bot()
    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("card:viewing:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock) as mock_spc:
        await bot.handle_card_callback(callback, state)

        mock_spc.assert_awaited_once()
        call_kwargs = mock_spc.call_args.kwargs
        assert call_kwargs["service_key"] == "viewing"
        assert call_kwargs["viewing_objects"][0]["id"] == "prop-42"


async def test_card_ask_starts_phone_collection_manager_question() -> None:
    """card:ask:{id} → start_phone_collection with service_key=manager_question."""
    bot = _create_bot()
    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("card:ask:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock) as mock_spc:
        await bot.handle_card_callback(callback, state)

        mock_spc.assert_awaited_once()
        call_kwargs = mock_spc.call_args.kwargs
        assert call_kwargs["service_key"] == "manager_question"
        assert call_kwargs["viewing_objects"][0]["id"] == "prop-42"


async def test_card_callback_no_results_in_state() -> None:
    """card:viewing with no results in state → viewing_objects is None or []."""
    bot = _create_bot()
    state = _make_state({})
    callback = _make_callback("card:viewing:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock) as mock_spc:
        await bot.handle_card_callback(callback, state)

        call_kwargs = mock_spc.call_args.kwargs
        vo = call_kwargs.get("viewing_objects")
        assert vo is None or vo == []


async def test_card_callback_fallbacks_to_favorites_when_state_missing() -> None:
    """card:viewing uses favorites data when apartment_results is absent."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.list = AsyncMock(
        return_value=[
            MagicMock(
                property_id="prop-42",
                property_data={
                    "complex_name": "Ocean Vista",
                    "property_type": "Studio",
                    "area_m2": 55,
                    "price_eur": 250000,
                },
            )
        ]
    )
    state = _make_state({})
    callback = _make_callback("card:viewing:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock) as mock_spc:
        await bot.handle_card_callback(callback, state)

        call_kwargs = mock_spc.call_args.kwargs
        assert call_kwargs["service_key"] == "viewing"
        assert call_kwargs["viewing_objects"][0]["id"] == "prop-42"
        bot._favorites_service.list.assert_awaited_once_with(telegram_id=12345)


async def test_card_callback_unknown_action_answers_empty() -> None:
    """card:unknown:{id} → just answer() without crash."""
    bot = _create_bot()
    state = _make_state({})
    callback = _make_callback("card:unknown:prop-42")

    _patch = "telegram_bot.handlers.phone_collector.start_phone_collection"
    with patch(_patch, new_callable=AsyncMock) as mock_spc:
        await bot.handle_card_callback(callback, state)

        mock_spc.assert_not_awaited()
        callback.answer.assert_awaited()


async def test_card_callback_malformed_data_answers_empty() -> None:
    """card (no parts) → answer() without crash."""
    bot = _create_bot()
    state = _make_state({})
    callback = _make_callback("card")

    await bot.handle_card_callback(callback, state)

    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_card_viewing_starts_dialog_with_edit_mode() -> None:
    """card:viewing should start ViewingSG with ShowMode.EDIT to edit card in-place."""
    from aiogram_dialog import ShowMode

    bot = _create_bot()
    state = _make_state({"apartment_results": [_sample_result("prop-42")]})
    callback = _make_callback("card:viewing:prop-42")
    dialog_manager = AsyncMock()

    await bot.handle_card_callback(callback, state, dialog_manager=dialog_manager)

    dialog_manager.start.assert_awaited_once()
    call_kwargs = dialog_manager.start.call_args.kwargs
    assert call_kwargs.get("show_mode") == ShowMode.EDIT
