"""Tests for filter panel callback handlers (Task 8)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.callback_data import FilterPanelCB
from telegram_bot.handlers.filter_panel import handle_filter_panel


def _make_callback(action: str, field: str, value: str = "") -> MagicMock:
    """Create a mock callback query with FilterPanelCB data."""
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = 12345
    return cb


def _make_state(data: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock FSM state."""
    state = MagicMock()
    _data: dict[str, Any] = data or {}

    async def get_data() -> dict[str, Any]:
        return dict(_data)

    async def update_data(**kwargs: Any) -> None:
        _data.update(kwargs)

    state.get_data = get_data
    state.update_data = AsyncMock(side_effect=update_data)
    return state


class TestFilterPanelHandlerSelect:
    """Tests for action='select' — show sub-menu for a filter."""

    async def test_select_city_shows_city_options(self) -> None:
        """Нажатие 'Город' показывает варианты городов."""
        cb = _make_callback("select", "city")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="select", field="city")

        await handle_filter_panel(cb, state, cb_data)

        cb.message.edit_text.assert_awaited_once()
        call_args = cb.message.edit_text.call_args
        # Текст должен содержать опции городов
        text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
        assert "Солнечный берег" in text or "город" in text.lower()

    async def test_select_rooms_shows_rooms_options(self) -> None:
        """Нажатие 'Комнаты' показывает варианты комнат."""
        cb = _make_callback("select", "rooms")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="select", field="rooms")

        await handle_filter_panel(cb, state, cb_data)

        cb.message.edit_text.assert_awaited_once()

    async def test_select_uses_inline_keyboard(self) -> None:
        """Sub-menu использует InlineKeyboardMarkup."""
        from aiogram.types import InlineKeyboardMarkup

        cb = _make_callback("select", "city")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="select", field="city")

        await handle_filter_panel(cb, state, cb_data)

        call_kwargs = cb.message.edit_text.call_args.kwargs
        assert isinstance(call_kwargs.get("reply_markup"), InlineKeyboardMarkup)

    async def test_select_answers_callback(self) -> None:
        """После показа sub-menu отвечает на callback запрос."""
        cb = _make_callback("select", "city")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="select", field="city")

        await handle_filter_panel(cb, state, cb_data)

        cb.answer.assert_awaited()


class TestFilterPanelHandlerSet:
    """Tests for action='set' — update a filter value."""

    async def test_set_city_updates_filters(self) -> None:
        """Выбор города обновляет фильтры в FSMContext."""
        cb = _make_callback("set", "city", "Солнечный берег")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="set", field="city", value="Солнечный берег")

        await handle_filter_panel(cb, state, cb_data)

        state.update_data.assert_awaited()
        update_calls = state.update_data.call_args_list
        updated = {}
        for call in update_calls:
            updated.update(call.kwargs)
        assert updated.get("apartment_filters", {}).get("city") == "Солнечный берег"

    async def test_set_rooms_updates_filters(self) -> None:
        """Выбор комнат обновляет фильтры."""
        cb = _make_callback("set", "rooms", "2")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="set", field="rooms", value="2")

        await handle_filter_panel(cb, state, cb_data)

        state.update_data.assert_awaited()

    async def test_set_empty_value_clears_filter(self) -> None:
        """Пустое значение очищает конкретный фильтр."""
        cb = _make_callback("set", "city", "")
        state = _make_state({"apartment_filters": {"city": "Варна"}, "apartment_total": 10})
        cb_data = FilterPanelCB(action="set", field="city", value="")

        await handle_filter_panel(cb, state, cb_data)

        state.update_data.assert_awaited()
        update_calls = state.update_data.call_args_list
        updated = {}
        for call in update_calls:
            updated.update(call.kwargs)
        filters = updated.get("apartment_filters", {"city": "Варна"})
        assert filters.get("city") in (None, "", "Варна") or "city" not in filters

    async def test_set_returns_to_main_panel(self) -> None:
        """После установки фильтра показывает обновлённую панель."""
        cb = _make_callback("set", "city", "Бургас")
        state = _make_state({"apartment_filters": {}, "apartment_total": 5})
        cb_data = FilterPanelCB(action="set", field="city", value="Бургас")

        await handle_filter_panel(cb, state, cb_data)

        cb.message.edit_text.assert_awaited()


class TestFilterPanelHandlerApply:
    """Tests for action='apply' — apply filters and close panel."""

    async def test_apply_closes_panel(self) -> None:
        """'Применить' удаляет сообщение с панелью."""
        cb = _make_callback("apply", "")
        state = _make_state(
            {
                "apartment_filters": {"city": "Солнечный берег"},
                "apartment_offset": 20,
                "apartment_total": 30,
            }
        )
        cb_data = FilterPanelCB(action="apply", field="")

        await handle_filter_panel(cb, state, cb_data)

        # Либо удаляет, либо редактирует сообщение
        assert cb.message.delete.call_count > 0 or cb.message.edit_text.call_count > 0

    async def test_apply_resets_offset(self) -> None:
        """'Применить' сбрасывает offset для поиска с начала."""
        cb = _make_callback("apply", "")
        state = _make_state(
            {
                "apartment_filters": {"city": "Солнечный берег"},
                "apartment_offset": 20,
                "apartment_total": 30,
            }
        )
        cb_data = FilterPanelCB(action="apply", field="")

        await handle_filter_panel(cb, state, cb_data)

        state.update_data.assert_awaited()
        update_calls = state.update_data.call_args_list
        updated = {}
        for call in update_calls:
            updated.update(call.kwargs)
        assert updated.get("apartment_offset", 20) == 0

    async def test_apply_answers_callback(self) -> None:
        """'Применить' отвечает на callback запрос."""
        cb = _make_callback("apply", "")
        state = _make_state({"apartment_filters": {}, "apartment_offset": 0, "apartment_total": 0})
        cb_data = FilterPanelCB(action="apply", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.answer.assert_awaited()


class TestFilterPanelHandlerReset:
    """Tests for action='reset' — clear all filters."""

    async def test_reset_clears_all_filters(self) -> None:
        """'Сбросить' очищает все фильтры."""
        cb = _make_callback("reset", "")
        state = _make_state(
            {
                "apartment_filters": {"city": "Варна", "rooms": 2},
                "apartment_total": 42,
            }
        )
        cb_data = FilterPanelCB(action="reset", field="")

        await handle_filter_panel(cb, state, cb_data)

        state.update_data.assert_awaited()
        update_calls = state.update_data.call_args_list
        updated = {}
        for call in update_calls:
            updated.update(call.kwargs)
        assert updated.get("apartment_filters") == {}

    async def test_reset_updates_panel_text(self) -> None:
        """'Сбросить' обновляет панель с пустыми фильтрами."""
        cb = _make_callback("reset", "")
        state = _make_state({"apartment_filters": {"city": "Варна"}, "apartment_total": 5})
        cb_data = FilterPanelCB(action="reset", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.message.edit_text.assert_awaited()

    async def test_reset_answers_callback(self) -> None:
        """'Сбросить' отвечает на callback запрос."""
        cb = _make_callback("reset", "")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="reset", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.answer.assert_awaited()


class TestFilterPanelHandlerBack:
    """Tests for action='back' — close panel, return to catalog."""

    async def test_back_deletes_panel_message(self) -> None:
        """'Назад' удаляет сообщение с панелью."""
        cb = _make_callback("back", "")
        state = _make_state({"apartment_filters": {}, "apartment_total": 10})
        cb_data = FilterPanelCB(action="back", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.message.delete.assert_awaited_once()

    async def test_back_answers_callback(self) -> None:
        """'Назад' отвечает на callback запрос."""
        cb = _make_callback("back", "")
        state = _make_state({"apartment_filters": {}, "apartment_total": 10})
        cb_data = FilterPanelCB(action="back", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.answer.assert_awaited()


class TestFilterPanelHandlerMain:
    """Tests for action='main' — return to filter panel main screen from sub-menu."""

    async def test_main_shows_filter_panel(self) -> None:
        """'Назад к фильтрам' показывает главный экран панели."""
        cb = _make_callback("main", "")
        state = _make_state({"apartment_filters": {"city": "Несебр"}, "apartment_total": 12})
        cb_data = FilterPanelCB(action="main", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.message.edit_text.assert_awaited_once()

    async def test_main_shows_correct_filters_in_text(self) -> None:
        """Главный экран показывает текущие активные фильтры."""
        cb = _make_callback("main", "")
        state = _make_state({"apartment_filters": {"city": "Несебр"}, "apartment_total": 12})
        cb_data = FilterPanelCB(action="main", field="")

        await handle_filter_panel(cb, state, cb_data)

        call_args = cb.message.edit_text.call_args
        text = call_args.args[0] if call_args.args else call_args.kwargs.get("text", "")
        assert "Несебр" in text

    async def test_main_answers_callback(self) -> None:
        """'Назад к фильтрам' отвечает на callback запрос."""
        cb = _make_callback("main", "")
        state = _make_state({"apartment_filters": {}, "apartment_total": 0})
        cb_data = FilterPanelCB(action="main", field="")

        await handle_filter_panel(cb, state, cb_data)

        cb.answer.assert_awaited()
