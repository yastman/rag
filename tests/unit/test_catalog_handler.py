"""Tests for catalog_router SDK-based handlers (StateFilter + F.text)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")


def _make_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


def _make_message() -> MagicMock:
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.from_user = MagicMock(id=123)
    return msg


_APT = {
    "id": "apt-1",
    "payload": {
        "complex_name": "Test",
        "city": "Солнечный берег",
        "property_type": "Студия",
        "floor": 2,
        "area_m2": 45,
        "view_tags": [],
        "view_primary": "sea",
        "price_eur": 55000,
        "rooms": 1,
    },
}


# ============================================================
# handle_catalog_more
# ============================================================


class TestCatalogMoreHandler:
    async def test_sends_next_cards(self):
        """'Показать ещё' sends next batch of property cards."""
        from telegram_bot.handlers.catalog_router import handle_catalog_more

        new_page = [_APT] * 5
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(
            return_value=(new_page, 30, 65000.0, ["apt-1"]),
        )
        property_bot = MagicMock()
        property_bot._apartments_service = mock_svc
        property_bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "apartment_offset": 10,
                "apartment_total": 30,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {"city": "Солнечный берег"},
                "apartment_scroll_seen_ids": ["id-prev"],
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        assert property_bot._send_property_card.await_count == 5

    async def test_updates_keyboard_counter(self):
        """After sending cards, updates ReplyKeyboard with new counter."""
        from aiogram.types import ReplyKeyboardMarkup

        from telegram_bot.handlers.catalog_router import handle_catalog_more

        new_page = [_APT] * 10
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(
            return_value=(new_page, 30, 65000.0, ["apt-1"]),
        )
        property_bot = MagicMock()
        property_bot._apartments_service = mock_svc
        property_bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "apartment_offset": 10,
                "apartment_total": 30,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {},
                "apartment_scroll_seen_ids": [],
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        last_call = message.answer.call_args_list[-1]
        kb = last_call.kwargs.get("reply_markup")
        assert isinstance(kb, ReplyKeyboardMarkup)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "20 из 30" in button_texts

    async def test_all_shown_hides_more_button(self):
        """When all shown, 'Показать ещё' row is removed from keyboard."""
        from telegram_bot.handlers.catalog_router import handle_catalog_more

        new_page = [_APT] * 5
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(
            return_value=(new_page, 15, None, ["apt-1"]),
        )
        property_bot = MagicMock()
        property_bot._apartments_service = mock_svc
        property_bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "apartment_offset": 10,
                "apartment_total": 15,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {},
                "apartment_scroll_seen_ids": [],
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        last_call = message.answer.call_args_list[-1]
        kb = last_call.kwargs.get("reply_markup")
        assert len(kb.keyboard) == 2  # filters+bookmarks and menu only
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert not any("Показать" in t for t in button_texts)

    async def test_no_more_does_nothing(self):
        """When all already shown, handler returns without sending cards."""
        from telegram_bot.handlers.catalog_router import handle_catalog_more

        property_bot = MagicMock()
        property_bot._apartments_service = MagicMock()
        property_bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "apartment_offset": 30,
                "apartment_total": 30,
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        property_bot._send_property_card.assert_not_awaited()

    async def test_no_service_does_nothing(self):
        """When property_bot has no _apartments_service, handler returns."""
        from telegram_bot.handlers.catalog_router import handle_catalog_more

        property_bot = MagicMock(spec=[])  # no attributes

        state = _make_state(
            {
                "apartment_offset": 0,
                "apartment_total": 30,
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        message.answer.assert_not_awaited()


# ============================================================
# handle_catalog_exit
# ============================================================


class TestCatalogExitHandler:
    async def test_exit_clears_state_and_restores_keyboard(self):
        """'Главное меню' clears FSM state and restores client keyboard."""
        from aiogram.types import ReplyKeyboardMarkup

        from telegram_bot.handlers.catalog_router import handle_catalog_exit

        state = _make_state({})
        message = _make_message()

        await handle_catalog_exit(message, state)

        state.set_state.assert_awaited_once_with(None)
        state.update_data.assert_awaited_once()
        update_kwargs = state.update_data.call_args.kwargs
        assert update_kwargs.get("apartment_offset") is None
        assert update_kwargs.get("apartment_total") is None
        assert update_kwargs.get("apartment_filters") is None

        kb = message.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(kb, ReplyKeyboardMarkup)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "🏠 Подобрать квартиру" in button_texts


# ============================================================
# handle_catalog_filters
# ============================================================


class TestCatalogFiltersHandler:
    async def test_sends_inline_filter_panel(self):
        """Filters button sends inline filter panel (stays in browsing state)."""
        from aiogram.types import InlineKeyboardMarkup

        from telegram_bot.handlers.catalog_router import handle_catalog_filters

        mock_svc = MagicMock()
        mock_svc.count_with_filters = AsyncMock(return_value=23)
        property_bot = MagicMock()
        property_bot._apartments_service = mock_svc

        state = _make_state(
            {
                "apartment_filters": {"city": "Солнечный берег", "rooms": 2},
                "apartment_total": 30,
            }
        )
        message = _make_message()

        await handle_catalog_filters(message, state, property_bot=property_bot)

        call = message.answer.call_args
        assert isinstance(call.kwargs.get("reply_markup"), InlineKeyboardMarkup)
        text = call.args[0] if call.args else call.kwargs.get("text", "")
        assert "Солнечный берег" in text


# ============================================================
# handle_catalog_bookmarks
# ============================================================


class TestCatalogBookmarksHandler:
    async def test_routes_to_handle_bookmarks(self):
        """'📌 Избранное' routes to property_bot._handle_bookmarks."""
        from telegram_bot.handlers.catalog_router import handle_catalog_bookmarks

        property_bot = MagicMock()
        property_bot._handle_bookmarks = AsyncMock()

        state = _make_state({})
        message = _make_message()

        await handle_catalog_bookmarks(message, state, property_bot=property_bot)

        property_bot._handle_bookmarks.assert_awaited_once_with(message, state)


# ============================================================
# handle_catalog_noop (counter button)
# ============================================================


class TestCatalogNoopHandler:
    async def test_noop_returns_silently(self):
        """Counter button 'N из M' does nothing."""
        from telegram_bot.handlers.catalog_router import handle_catalog_noop

        message = _make_message()
        message.text = "7 из 45"

        await handle_catalog_noop(message)

        message.answer.assert_not_awaited()


# ============================================================
# handle_catalog_more — list view mode
# ============================================================


class TestCatalogListViewMode:
    async def test_list_mode_sends_text(self):
        """In list view mode, sends formatted text instead of cards."""
        from telegram_bot.handlers.catalog_router import handle_catalog_more

        new_page = [_APT] * 5
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(
            return_value=(new_page, 30, 65000.0, ["apt-1"]),
        )
        property_bot = MagicMock()
        property_bot._apartments_service = mock_svc
        property_bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "apartment_offset": 10,
                "apartment_total": 30,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {},
                "apartment_scroll_seen_ids": [],
                "catalog_view_mode": "list",
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        # In list mode, cards are NOT sent individually
        property_bot._send_property_card.assert_not_awaited()
        # Instead, text message is sent
        assert message.answer.await_count == 1
        call = message.answer.call_args
        assert call.kwargs.get("parse_mode") == "HTML"
