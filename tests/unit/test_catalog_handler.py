"""Tests for catalog mode handlers in bot.py (Tasks 5 & 6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")


def _make_bot():
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        return PropertyBot.__new__(PropertyBot)


def _make_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    state.set_data = AsyncMock()
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
# Task 5: _handle_catalog_more
# ============================================================


class TestCatalogMoreHandler:
    async def test_sends_next_10_cards(self):
        """Кнопка 'Показать ещё 10' отправляет следующую пачку карточек."""
        bot = _make_bot()
        new_page = [_APT] * 5
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=(new_page, 30, 65000.0, ["apt-1"]))
        bot._apartments_service = mock_svc
        bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 10,
                "apartment_total": 30,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {"city": "Солнечный берег"},
                "apartment_scroll_seen_ids": ["id-prev"],
            }
        )
        message = _make_message()

        await bot._handle_catalog_more(message, state)

        assert bot._send_property_card.await_count == 5

    async def test_updates_keyboard_counter(self):
        """После отправки обновляет ReplyKeyboard с новым счётчиком."""
        from aiogram.types import ReplyKeyboardMarkup

        bot = _make_bot()
        new_page = [_APT] * 10
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=(new_page, 30, 65000.0, ["apt-1"]))
        bot._apartments_service = mock_svc
        bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 10,
                "apartment_total": 30,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {},
                "apartment_scroll_seen_ids": [],
            }
        )
        message = _make_message()

        await bot._handle_catalog_more(message, state)

        last_call = message.answer.call_args_list[-1]
        kb = last_call.kwargs.get("reply_markup")
        assert isinstance(kb, ReplyKeyboardMarkup)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "20 из 30" in button_texts

    async def test_all_shown_hides_more_button(self):
        """Когда всё показано, строка 'Показать ещё' исчезает из клавиатуры."""
        bot = _make_bot()
        new_page = [_APT] * 5
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=(new_page, 15, None, ["apt-1"]))
        bot._apartments_service = mock_svc
        bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 10,
                "apartment_total": 15,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {},
                "apartment_scroll_seen_ids": [],
            }
        )
        message = _make_message()

        await bot._handle_catalog_more(message, state)

        last_call = message.answer.call_args_list[-1]
        kb = last_call.kwargs.get("reply_markup")
        assert len(kb.keyboard) == 2  # no more row, just filters+bookmarks and menu
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert not any("Показать" in t for t in button_texts)

    async def test_no_more_does_nothing(self):
        """Если всё уже показано, handler не отправляет карточек."""
        bot = _make_bot()
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=([], 30, None, []))
        bot._apartments_service = mock_svc
        bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 30,
                "apartment_total": 30,
            }
        )
        message = _make_message()

        await bot._handle_catalog_more(message, state)

        bot._send_property_card.assert_not_awaited()


# ============================================================
# Task 6: _handle_catalog_exit and _handle_catalog_filters
# ============================================================


class TestCatalogExitHandler:
    async def test_exit_restores_client_keyboard(self):
        """'Главное меню' возвращает обычный ReplyKeyboard."""
        from aiogram.types import ReplyKeyboardMarkup

        bot = _make_bot()
        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 20,
                "apartment_total": 30,
                "apartment_filters": {"city": "Солнечный берег"},
            }
        )
        message = _make_message()

        await bot._handle_catalog_exit(message, state)

        state.update_data.assert_awaited()
        update_call = state.update_data.call_args.kwargs
        assert update_call.get("catalog_mode") is False

        kb = message.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(kb, ReplyKeyboardMarkup)
        button_texts = [btn.text for row in kb.keyboard for btn in row]
        assert "🏠 Подобрать квартиру" in button_texts

    async def test_exit_clears_apartment_state(self):
        """Выход из каталога очищает apartment_* ключи FSMContext."""
        bot = _make_bot()
        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 20,
                "apartment_total": 30,
            }
        )
        message = _make_message()

        await bot._handle_catalog_exit(message, state)

        update_call = state.update_data.call_args.kwargs
        assert update_call.get("apartment_offset") is None
        assert update_call.get("apartment_total") is None
        assert update_call.get("catalog_mode") is False


class TestCatalogNoopHandler:
    async def test_noop_counter_returns_silently(self):
        """Counter button 'N из M' should return without any action."""
        bot = _make_bot()
        bot._handle_catalog_more = AsyncMock()
        bot._handle_catalog_exit = AsyncMock()
        bot._handle_bookmarks = AsyncMock()

        state = _make_state({"catalog_mode": True})
        message = _make_message()
        message.text = "7 из 45"

        await bot.handle_menu_button(message, state)

        bot._handle_catalog_more.assert_not_awaited()
        bot._handle_catalog_exit.assert_not_awaited()
        bot._handle_bookmarks.assert_not_awaited()
        message.answer.assert_not_awaited()


class TestCatalogBookmarksHandler:
    async def test_bookmarks_routes_to_handle_bookmarks(self):
        """'📌 Избранное' should route to _handle_bookmarks via catalog dispatch."""
        bot = _make_bot()
        bot._handle_bookmarks = AsyncMock()

        state = _make_state({"catalog_mode": True})
        message = _make_message()
        message.text = "📌 Избранное"

        await bot._handle_catalog_dispatch(message, state)

        bot._handle_bookmarks.assert_awaited_once_with(message, state)


class TestCatalogFooterNoDuplicate:
    async def test_catalog_more_sends_status_with_keyboard(self):
        """_handle_catalog_more sends 'Показано X из Y' with catalog keyboard."""
        from aiogram.types import ReplyKeyboardMarkup

        bot = _make_bot()
        new_page = [_APT] * 5
        mock_svc = MagicMock()
        mock_svc.scroll_with_filters = AsyncMock(return_value=(new_page, 30, 65000.0, ["apt-1"]))
        bot._apartments_service = mock_svc
        bot._send_property_card = AsyncMock()

        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_offset": 10,
                "apartment_total": 30,
                "apartment_next_offset": 55000.0,
                "apartment_filters": {},
                "apartment_scroll_seen_ids": [],
            }
        )
        message = _make_message()

        await bot._handle_catalog_more(message, state)

        last_call = message.answer.call_args_list[-1]
        text = last_call.args[0] if last_call.args else last_call.kwargs.get("text", "")
        assert "15 из 30" in text
        reply_markup = last_call.kwargs.get("reply_markup")
        assert isinstance(reply_markup, ReplyKeyboardMarkup)


class TestCatalogFiltersHandler:
    async def test_handle_catalog_filters_starts_funnel_summary(self):
        """Filters button should start FunnelSG.summary dialog with saved data."""
        bot = _make_bot()

        state = _make_state(
            {
                "catalog_mode": True,
                "funnel_data": {"city": "varna", "budget": "mid"},
                "apartment_filters": {"city": "varna"},
            }
        )
        message = _make_message()
        dialog_manager = AsyncMock()

        await bot._handle_catalog_filters(message, state, dialog_manager)

        dialog_manager.start.assert_called_once()
        call_args = dialog_manager.start.call_args
        from telegram_bot.dialogs.states import FunnelSG

        assert call_args[0][0] == FunnelSG.summary

    async def test_filters_sends_inline_panel(self):
        """'Фильтры' отправляет inline-сообщение с текущими фильтрами."""
        from aiogram.types import InlineKeyboardMarkup

        bot = _make_bot()
        mock_svc = MagicMock()
        mock_svc.count_with_filters = AsyncMock(return_value=23)
        bot._apartments_service = mock_svc

        state = _make_state(
            {
                "catalog_mode": True,
                "apartment_filters": {"city": "Солнечный берег", "rooms": 2},
                "apartment_total": 30,
            }
        )
        message = _make_message()

        await bot._handle_catalog_filters(message, state)

        call = message.answer.call_args
        assert isinstance(call.kwargs.get("reply_markup"), InlineKeyboardMarkup)
        text = call.args[0] if call.args else call.kwargs.get("text", "")
        assert "Солнечный берег" in text
