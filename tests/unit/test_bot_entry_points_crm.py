# tests/unit/test_bot_entry_points_crm.py
"""Tests for bot.py CRM entry points — viewing fork, cta callbacks, context passing (#628)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig


# ---------------------------------------------------------------------------
# Helpers
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


def _make_message(text: str = "test") -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock(id=12345, first_name="Test")
    msg.answer = AsyncMock()
    return msg


def _make_callback(data: str, user_id: int = 12345) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_favorite(property_id: str, **data: object) -> SimpleNamespace:
    return SimpleNamespace(
        property_id=property_id,
        property_data={
            "complex_name": data.get("complex_name", "Test Complex"),
            "property_type": data.get("property_type", "Apartment"),
            "area_m2": data.get("area_m2", 60),
            "price_eur": data.get("price_eur", 200000),
        },
    )


def _fav_bot(favorites: list | None = None) -> PropertyBot:
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    bot._favorites_service.list = AsyncMock(return_value=favorites or [])
    bot._favorites_service.add = AsyncMock(return_value={"id": 1, "property_id": "prop-0"})
    bot._favorites_service.remove = AsyncMock()
    return bot


# ---------------------------------------------------------------------------
# Test: _handle_viewing — fork keyboard
# ---------------------------------------------------------------------------


async def test_handle_viewing_shows_fork_keyboard() -> None:
    """_handle_viewing sends InlineKeyboard with 2 buttons (choose_objects, phone)."""
    bot = _create_bot()
    state = _make_state()
    msg = _make_message()

    await bot._handle_viewing(msg, state)

    msg.answer.assert_awaited_once()
    call_kwargs = msg.answer.call_args
    # Check text
    assert "объект" in call_kwargs[0][0].lower() or "конкретн" in call_kwargs[0][0].lower()
    # Check keyboard has 2 rows
    keyboard = call_kwargs[1]["reply_markup"]
    assert len(keyboard.inline_keyboard) == 2
    # Check callback_data values
    button_datas = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "viewing:choose_objects" in button_datas
    assert "viewing:phone" in button_datas


# ---------------------------------------------------------------------------
# Test: viewing:phone -> start_phone_collection(service_key="viewing")
# ---------------------------------------------------------------------------


async def test_viewing_phone_callback_starts_phone_collection() -> None:
    """viewing:phone -> start_phone_collection called with service_key='viewing'."""
    bot = _create_bot()
    state = _make_state()
    cb = _make_callback("viewing:phone")

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection",
        new=AsyncMock(),
    ) as mock_collect:
        await bot.handle_viewing_callback(cb, state)

    mock_collect.assert_awaited_once_with(cb, state, service_key="viewing")


# ---------------------------------------------------------------------------
# Test: viewing:choose_objects -> redirect to apartment search
# ---------------------------------------------------------------------------


async def test_viewing_choose_objects_starts_search() -> None:
    """viewing:choose_objects -> routes to apartment search pipeline."""
    bot = _create_bot()
    state = _make_state()
    cb = _make_callback("viewing:choose_objects")

    with patch.object(bot, "handle_menu_action_text", new=AsyncMock()) as mock_action:
        await bot.handle_viewing_callback(cb, state)

    mock_action.assert_awaited_once_with(cb.message, "Подбери апартаменты")
    cb.answer.assert_awaited_once()


async def test_viewing_choose_objects_no_message() -> None:
    """viewing:choose_objects with message=None -> handle_menu_action_text not called, answer still called."""
    bot = _create_bot()
    state = _make_state()
    cb = _make_callback("viewing:choose_objects")
    cb.message = None

    with patch.object(bot, "handle_menu_action_text", new=AsyncMock()) as mock_action:
        await bot.handle_viewing_callback(cb, state)

    mock_action.assert_not_awaited()
    cb.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: cta:manager -> start_phone_collection(service_key="manager")
# ---------------------------------------------------------------------------


async def test_cta_manager_starts_phone_collection() -> None:
    """cta:manager -> start_phone_collection called with service_key='manager'."""
    bot = _create_bot()
    state = _make_state()
    cb = _make_callback("cta:manager")

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection",
        new=AsyncMock(),
    ) as mock_collect:
        await bot.handle_cta_callback(cb, state)

    mock_collect.assert_awaited_once_with(cb, state, service_key="manager")


# ---------------------------------------------------------------------------
# Test: cta:get_offer:{param} -> service_key=param
# ---------------------------------------------------------------------------


async def test_cta_get_offer_passes_service_key() -> None:
    """cta:get_offer:installment -> start_phone_collection(service_key='installment')."""
    bot = _create_bot()
    state = _make_state()
    cb = _make_callback("cta:get_offer:installment")

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection",
        new=AsyncMock(),
    ) as mock_collect:
        await bot.handle_cta_callback(cb, state)

    mock_collect.assert_awaited_once_with(cb, state, service_key="installment")


# ---------------------------------------------------------------------------
# Test: results:viewing -> viewing_objects built from apartment_results
# ---------------------------------------------------------------------------


async def test_results_viewing_passes_objects_context() -> None:
    """results:viewing -> viewing_objects contains first 5 results from FSM state."""
    bot = _create_bot()
    results = [
        {
            "id": f"prop-{i}",
            "payload": {
                "complex_name": f"Complex {i}",
                "property_type": "Apartment",
                "area_m2": 60 + i * 5,
                "price_eur": 200000 + i * 10000,
            },
        }
        for i in range(7)  # 7 results, only first 5 should be passed
    ]
    state = _make_state({"apartment_results": results})
    cb = _make_callback("results:viewing")

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection",
        new=AsyncMock(),
    ) as mock_collect:
        await bot.handle_results_callback(cb, state)

    mock_collect.assert_awaited_once()
    kwargs = mock_collect.call_args[1]
    assert kwargs["service_key"] == "viewing"
    viewing_objects = kwargs["viewing_objects"]
    assert viewing_objects is not None
    assert len(viewing_objects) == 5
    assert viewing_objects[0]["id"] == "prop-0"
    assert viewing_objects[0]["complex_name"] == "Complex 0"
    assert viewing_objects[4]["id"] == "prop-4"


# ---------------------------------------------------------------------------
# Test: fav:viewing:{id} -> viewing_objects with single matched object
# ---------------------------------------------------------------------------


async def test_fav_viewing_passes_single_object() -> None:
    """fav:viewing:prop-42 -> viewing_objects contains exactly the matched favorite."""
    fav = _make_favorite("prop-42", complex_name="Sunset Tower", area_m2=85, price_eur=420000)
    bot = _fav_bot(favorites=[fav, _make_favorite("prop-99")])
    state = _make_state()
    cb = _make_callback("fav:viewing:prop-42")

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection",
        new=AsyncMock(),
    ) as mock_collect:
        await bot.handle_favorite_callback(cb, state)

    mock_collect.assert_awaited_once()
    kwargs = mock_collect.call_args[1]
    assert kwargs["service_key"] == "viewing"
    viewing_objects = kwargs["viewing_objects"]
    assert viewing_objects is not None
    assert len(viewing_objects) == 1
    assert viewing_objects[0]["id"] == "prop-42"
    assert viewing_objects[0]["complex_name"] == "Sunset Tower"
    assert viewing_objects[0]["area_m2"] == 85
    assert viewing_objects[0]["price_eur"] == 420000
