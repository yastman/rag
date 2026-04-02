"""Unit tests for service and CTA callback handlers."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch


def _make_config():
    """Create mock bot config."""
    from telegram_bot.config import BotConfig

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


def _create_bot():
    """Create PropertyBot with deps mocked."""
    from telegram_bot.bot import PropertyBot

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
    """Create a mock callback query."""
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.delete = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> MagicMock:
    """Create a mock FSM state."""
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.get_state = AsyncMock(return_value="SomeState:other")
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# Tests: handle_service_callback
# ---------------------------------------------------------------------------


async def test_service_callback_back_deletes_message():
    """svc:back should delete the message."""
    bot = _create_bot()

    cb = _make_callback("svc:back")
    i18n = MagicMock()

    await bot.handle_service_callback(cb, i18n=i18n)

    cb.message.delete.assert_awaited_once()
    cb.answer.assert_awaited_once()


async def test_service_callback_menu_shows_services_menu():
    """svc:menu should show the services menu."""
    bot = _create_bot()

    cb = _make_callback("svc:menu")
    i18n = MagicMock()
    i18n.get.return_value = "Choose a service:"

    with patch("telegram_bot.keyboards.services_keyboard.build_services_menu") as mock_build_menu:
        mock_menu = MagicMock()
        mock_build_menu.return_value = mock_menu
        await bot.handle_service_callback(cb, i18n=i18n)

    cb.message.edit_text.assert_awaited_once()
    i18n.get.assert_called_with("services-menu-text")


async def test_service_callback_service_shows_card():
    """svc:service:key should show the service card."""
    bot = _create_bot()

    cb = _make_callback("svc:service:passive_income")
    i18n = MagicMock()
    i18n.get.return_value = None

    mock_card = {"card_text": "Passive income description"}

    with patch("telegram_bot.services.content_loader.get_service_card", return_value=mock_card):
        with patch(
            "telegram_bot.keyboards.services_keyboard.build_service_card_buttons"
        ) as mock_build_buttons:
            mock_buttons = MagicMock()
            mock_build_buttons.return_value = mock_buttons
            await bot.handle_service_callback(cb, i18n=i18n)

    cb.message.edit_text.assert_awaited_once()


async def test_service_callback_unknown_action_answers_empty():
    """Unknown svc:action should answer with no alert."""
    bot = _create_bot()

    cb = _make_callback("svc:unknown:action")

    await bot.handle_service_callback(cb)

    cb.answer.assert_awaited_once()


async def test_service_callback_no_message_no_crash():
    """svc:back with no message should not crash."""
    bot = _create_bot()

    cb = _make_callback("svc:back")
    cb.message = None
    i18n = MagicMock()

    # Should not raise
    await bot.handle_service_callback(cb, i18n=i18n)

    cb.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: handle_cta_callback
# ---------------------------------------------------------------------------


async def test_cta_callback_get_offer_starts_phone_collection():
    """cta:get_offer should start phone collection."""
    bot = _create_bot()

    cb = _make_callback("cta:get_offer:some_service")
    state = _make_state()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await bot.handle_cta_callback(cb, state)

    mock_phone.assert_awaited_once()
    call_kwargs = mock_phone.call_args.kwargs
    assert call_kwargs.get("service_key") == "some_service"


async def test_cta_callback_manager_without_forum_bridge_calls_phone_collection():
    """cta:manager without forum_bridge should call start_phone_collection."""
    bot = _create_bot()
    bot._forum_bridge = None

    cb = _make_callback("cta:manager")
    state = _make_state()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await bot.handle_cta_callback(cb, state)

    mock_phone.assert_awaited_once()
    call_kwargs = mock_phone.call_args.kwargs
    assert call_kwargs.get("service_key") == "manager"


async def test_cta_callback_manager_without_forum_bridge_starts_phone_collection():
    """cta:manager without forum_bridge should start phone collection."""
    bot = _create_bot()
    bot._forum_bridge = None

    cb = _make_callback("cta:manager")
    state = _make_state()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await bot.handle_cta_callback(cb, state)

    mock_phone.assert_awaited_once()
    call_kwargs = mock_phone.call_args.kwargs
    assert call_kwargs.get("service_key") == "manager"


async def test_cta_callback_unknown_action_answers_empty():
    """Unknown cta:action should answer with no alert."""
    bot = _create_bot()

    cb = _make_callback("cta:unknown")
    state = _make_state()

    await bot.handle_cta_callback(cb, state)

    cb.answer.assert_awaited_once()


async def test_cta_callback_malformed_data_answers_empty():
    """Malformed cta:data should answer with no alert."""
    bot = _create_bot()

    cb = _make_callback("cta:")
    state = _make_state()

    # Should not raise
    await bot.handle_cta_callback(cb, state)

    cb.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: handle_results_callback
# ---------------------------------------------------------------------------


async def test_results_callback_answers_with_stale_text():
    """Results callback should answer with stale button text."""
    bot = _create_bot()

    cb = _make_callback("results:more")
    state = _make_state()

    await bot.handle_results_callback(cb, state)

    cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    cb.message.answer.assert_awaited_once()
    # Verify stale text was sent
    call_args = cb.message.answer.call_args
    assert "устаревшая" in call_args.args[0].lower() or "актуальное" in call_args.args[0].lower()


async def test_results_callback_no_message_no_crash():
    """Results callback with no message should not crash."""
    bot = _create_bot()

    cb = _make_callback("results:more")
    cb.message = None
    state = _make_state()

    # Should not raise
    await bot.handle_results_callback(cb, state)


# ---------------------------------------------------------------------------
# Tests: handle_fav_viewing
# ---------------------------------------------------------------------------


async def test_fav_viewing_starts_phone_collection():
    """fav:viewing:{id} should start phone collection with viewing objects."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()
    mock_fav_item = MagicMock()
    mock_fav_item.property_id = "prop-42"
    mock_fav_item.property_data = {
        "complex_name": "Test Property",
        "property_type": "Apartment",
        "area_m2": 50,
        "price_eur": 100000,
    }
    bot._favorites_service.list = AsyncMock(return_value=[mock_fav_item])

    cb = _make_callback("fav:viewing:prop-42")
    state = _make_state()

    callback_data = MagicMock()
    callback_data.apartment_id = "prop-42"

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await bot.handle_fav_viewing(cb, state, callback_data=callback_data)

    mock_phone.assert_awaited_once()
    call_kwargs = mock_phone.call_args.kwargs
    assert call_kwargs.get("service_key") == "viewing"
    assert len(call_kwargs.get("viewing_objects", [])) > 0


async def test_fav_viewing_no_favorites_service_answers_unavailable():
    """fav:viewing without favorites_service should answer unavailable."""
    bot = _create_bot()
    bot._favorites_service = None

    cb = _make_callback("fav:viewing:prop-42")
    state = _make_state()

    callback_data = MagicMock()
    callback_data.apartment_id = "prop-42"

    await bot.handle_fav_viewing(cb, state, callback_data=callback_data)

    cb.answer.assert_awaited_once_with("Закладки недоступны")


# ---------------------------------------------------------------------------
# Tests: handle_fav_viewing_all
# ---------------------------------------------------------------------------


async def test_fav_viewing_all_starts_phone_collection_with_all_favorites():
    """fav:viewing_all should start phone collection with all favorites."""
    bot = _create_bot()
    bot._favorites_service = MagicMock()

    mock_fav1 = MagicMock()
    mock_fav1.property_id = "prop-1"
    mock_fav1.property_data = {
        "complex_name": "Property 1",
        "property_type": "Apt",
        "area_m2": 40,
        "price_eur": 50000,
    }

    mock_fav2 = MagicMock()
    mock_fav2.property_id = "prop-2"
    mock_fav2.property_data = {
        "complex_name": "Property 2",
        "property_type": "Studio",
        "area_m2": 30,
        "price_eur": 40000,
    }

    bot._favorites_service.list = AsyncMock(return_value=[mock_fav1, mock_fav2])

    cb = _make_callback("fav:viewing_all")
    state = _make_state()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_phone:
        await bot.handle_fav_viewing_all(cb, state)

    mock_phone.assert_awaited_once()
    call_kwargs = mock_phone.call_args.kwargs
    assert call_kwargs.get("service_key") == "viewing"
    assert len(call_kwargs.get("viewing_objects", [])) == 2


async def test_fav_viewing_all_no_favorites_service_answers_unavailable():
    """fav:viewing_all without favorites_service should answer unavailable."""
    bot = _create_bot()
    bot._favorites_service = None

    cb = _make_callback("fav:viewing_all")
    state = _make_state()

    await bot.handle_fav_viewing_all(cb, state)

    cb.answer.assert_awaited_once_with("Закладки недоступны")
