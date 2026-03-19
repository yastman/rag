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
    state.clear = AsyncMock()
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
        assert any("20 из 30" in t for t in button_texts)

    async def test_cards_mode_no_counter_text(self):
        """In cards mode, status message should NOT contain 'Показано N из M'."""
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
            }
        )
        message = _make_message()

        await handle_catalog_more(message, state, property_bot=property_bot)

        last_call = message.answer.call_args_list[-1]
        text = last_call.args[0] if last_call.args else last_call.kwargs.get("text", "")
        assert "Показано" not in text

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
        assert len(kb.keyboard) == 3  # filters+bookmarks, viewing+manager, menu
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
        """Fallback exit clears FSM state and restores client keyboard."""
        from aiogram.types import ReplyKeyboardMarkup

        from telegram_bot.handlers.catalog_router import handle_catalog_exit

        state = _make_state({})
        message = _make_message()

        await handle_catalog_exit(message, state)

        state.clear.assert_awaited_once()
        state.set_state.assert_not_awaited()
        state.update_data.assert_not_awaited()

        kb = message.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(kb, ReplyKeyboardMarkup)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "🏠 Подобрать квартиру" in button_texts

    async def test_exit_starts_client_root_with_reset_stack(self):
        """Catalog exit should rejoin the SDK client root when dialog_manager is available."""
        from aiogram_dialog import StartMode

        from telegram_bot.dialogs.states import ClientMenuSG
        from telegram_bot.handlers.catalog_router import handle_catalog_exit

        state = _make_state({})
        message = _make_message()
        dialog_manager = AsyncMock()

        await handle_catalog_exit(message, state, dialog_manager=dialog_manager)

        state.clear.assert_awaited_once()
        dialog_manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)
        message.answer.assert_not_awaited()


# ============================================================
# handle_catalog_filters
# ============================================================


class TestCatalogFiltersHandler:
    async def test_launches_filter_dialog(self):
        """Filters button launches FilterDialog via dialog_manager.start(FilterSG.hub)."""
        from telegram_bot.dialogs.states import FilterSG
        from telegram_bot.handlers.catalog_router import handle_catalog_filters

        state = _make_state(
            {
                "apartment_filters": {"city": "Солнечный берег", "rooms": 2},
                "apartment_total": 30,
            }
        )
        message = _make_message()
        dialog_manager = MagicMock()
        dialog_manager.start = AsyncMock()

        await handle_catalog_filters(message, state, dialog_manager=dialog_manager)

        dialog_manager.start.assert_awaited_once()
        call_args = dialog_manager.start.call_args
        assert call_args.args[0] == FilterSG.hub
        assert call_args.kwargs.get("data") == {"filters": {"city": "Солнечный берег", "rooms": 2}}


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
# handle_catalog_viewing
# ============================================================


class TestCatalogViewingHandler:
    async def test_routes_to_handle_viewing(self):
        """'📅 Запись на осмотр' routes to property_bot._handle_viewing."""
        from telegram_bot.handlers.catalog_router import handle_catalog_viewing

        property_bot = MagicMock()
        property_bot._handle_viewing = AsyncMock()

        state = _make_state({})
        message = _make_message()
        dialog_manager = MagicMock()

        await handle_catalog_viewing(
            message, state, property_bot=property_bot, dialog_manager=dialog_manager
        )

        property_bot._handle_viewing.assert_awaited_once_with(message, state, dialog_manager)

    async def test_no_property_bot_does_nothing(self):
        """Without property_bot, handler does nothing."""
        from telegram_bot.handlers.catalog_router import handle_catalog_viewing

        state = _make_state({})
        message = _make_message()

        await handle_catalog_viewing(message, state, property_bot=None)

        message.answer.assert_not_awaited()


# ============================================================
# handle_catalog_manager
# ============================================================


class TestCatalogManagerHandler:
    async def test_routes_to_handle_manager(self):
        """'👤 Написать менеджеру' routes to property_bot._handle_manager."""
        from telegram_bot.handlers.catalog_router import handle_catalog_manager

        property_bot = MagicMock()
        property_bot._handle_manager = AsyncMock()

        state = _make_state({})
        message = _make_message()
        dialog_manager = MagicMock()

        await handle_catalog_manager(
            message, state, property_bot=property_bot, dialog_manager=dialog_manager
        )

        property_bot._handle_manager.assert_awaited_once_with(
            message, state=state, dialog_manager=dialog_manager
        )

    async def test_no_property_bot_does_nothing(self):
        """Without property_bot, handler does nothing."""
        from telegram_bot.handlers.catalog_router import handle_catalog_manager

        state = _make_state({})
        message = _make_message()

        await handle_catalog_manager(message, state, property_bot=None)

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


# ============================================================
# build_catalog_keyboard — viewing + manager buttons
# ============================================================


class TestCatalogKeyboardButtons:
    def test_keyboard_has_viewing_and_manager_buttons(self):
        """Catalog keyboard includes viewing and manager buttons."""
        from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

        kb = build_catalog_keyboard(shown=5, total=20)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "📅 Запись на осмотр" in button_texts
        assert "👤 Написать менеджеру" in button_texts

    def test_keyboard_viewing_manager_row_present_when_no_more(self):
        """Even when all shown, viewing/manager row is present."""
        from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

        kb = build_catalog_keyboard(shown=20, total=20)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "📅 Запись на осмотр" in button_texts
        assert "👤 Написать менеджеру" in button_texts
        assert not any("Показать" in t for t in button_texts)
