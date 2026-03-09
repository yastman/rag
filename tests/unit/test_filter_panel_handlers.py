"""Tests for inline filter panel callback handlers (Task 8)."""

from __future__ import annotations

from unittest.mock import AsyncMock


# --- Router creation ---


def test_create_filter_panel_router_returns_router() -> None:
    """create_filter_panel_router() returns an aiogram Router."""
    from aiogram import Router

    from telegram_bot.handlers.filter_panel import create_filter_panel_router

    router = create_filter_panel_router()
    assert isinstance(router, Router)
    assert router.name == "filter_panel"


# --- Handler imports ---


def test_handler_functions_exist() -> None:
    """All required handler functions are importable."""
    from telegram_bot.handlers.filter_panel import (  # noqa: F401
        on_filter_panel_apply,
        on_filter_panel_back,
        on_filter_panel_reset,
        on_filter_panel_select,
        on_filter_panel_set,
    )


# --- on_filter_panel_select: shows sub-menu for a filter ---


async def test_select_city_edits_message_with_options() -> None:
    """Pressing 'Город' replaces message with city options keyboard."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_select

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {"city": "Несебр"}})

    cb_data = FilterPanelCB(action="select", field="city")
    await on_filter_panel_select(callback, state, cb_data)

    callback.message.edit_text.assert_called_once()
    call_kwargs = callback.message.edit_text.call_args
    # Should edit with some text and inline keyboard
    assert call_kwargs is not None
    callback.answer.assert_called()


async def test_select_rooms_edits_message_with_keyboard() -> None:
    """Pressing 'Комнаты' edits with rooms options."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_select

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}})

    cb_data = FilterPanelCB(action="select", field="rooms")
    await on_filter_panel_select(callback, state, cb_data)

    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called()


async def test_select_unknown_field_answers_gracefully() -> None:
    """Unknown field does not crash — answers with notification."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_select

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}})

    cb_data = FilterPanelCB(action="select", field="unknown_field")
    await on_filter_panel_select(callback, state, cb_data)

    callback.answer.assert_called()


# --- on_filter_panel_set: updates filters in FSMContext ---


async def test_set_city_updates_fsm_filters() -> None:
    """Setting city updates apartment_filters in FSMContext."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_set

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}})

    cb_data = FilterPanelCB(action="set", field="city", value="Солнечный берег")
    await on_filter_panel_set(callback, state, cb_data)

    state.update_data.assert_called()
    call_kwargs = state.update_data.call_args
    updated = call_kwargs.kwargs.get("apartment_filters") or (
        call_kwargs.args[0] if call_kwargs.args else {}
    )
    assert updated.get("city") == "Солнечный берег"


async def test_set_empty_value_removes_filter() -> None:
    """Setting empty value removes that filter key."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_set

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {"city": "Несебр", "rooms": 2}})

    cb_data = FilterPanelCB(action="set", field="city", value="")
    await on_filter_panel_set(callback, state, cb_data)

    state.update_data.assert_called()
    call_kwargs = state.update_data.call_args
    updated = call_kwargs.kwargs.get("apartment_filters") or (
        call_kwargs.args[0] if call_kwargs.args else {}
    )
    assert "city" not in updated


async def test_set_rooms_converts_to_int() -> None:
    """Setting rooms converts string value to int."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_set

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}})

    cb_data = FilterPanelCB(action="set", field="rooms", value="2")
    await on_filter_panel_set(callback, state, cb_data)

    state.update_data.assert_called()
    call_kwargs = state.update_data.call_args
    updated = call_kwargs.kwargs.get("apartment_filters") or (
        call_kwargs.args[0] if call_kwargs.args else {}
    )
    assert updated.get("rooms") == 2


async def test_set_goes_back_to_panel_after_update() -> None:
    """After setting a filter, message is edited back to main panel."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_set

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}})

    cb_data = FilterPanelCB(action="set", field="city", value="Варна")
    await on_filter_panel_set(callback, state, cb_data)

    # Should edit message to show updated panel
    callback.message.edit_text.assert_called_once()


# --- on_filter_panel_apply: close panel, re-search ---


async def test_apply_resets_offset_to_zero() -> None:
    """Apply resets apartment_offset to 0 for fresh search."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_apply

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "apartment_filters": {"city": "Солнечный берег"},
            "apartment_offset": 20,
        }
    )

    cb_data = FilterPanelCB(action="apply", field="")
    await on_filter_panel_apply(callback, state, cb_data)

    state.update_data.assert_called()
    # Check offset reset
    all_calls = state.update_data.call_args_list
    updated_offsets = [
        c.kwargs.get("apartment_offset")
        for c in all_calls
        if "apartment_offset" in (c.kwargs or {})
    ]
    assert any(v == 0 for v in updated_offsets)


async def test_apply_deletes_panel_message() -> None:
    """Apply closes the inline panel (deletes the message)."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_apply

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}})

    cb_data = FilterPanelCB(action="apply", field="")
    await on_filter_panel_apply(callback, state, cb_data)

    callback.message.delete.assert_called_once()


# --- on_filter_panel_reset: clears all filters ---


async def test_reset_clears_all_filters() -> None:
    """Reset empties apartment_filters dict."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_reset

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {"city": "X", "rooms": 2}})

    cb_data = FilterPanelCB(action="reset", field="")
    await on_filter_panel_reset(callback, state, cb_data)

    state.update_data.assert_called()
    call_kwargs = state.update_data.call_args
    assert "apartment_filters" in call_kwargs.kwargs
    assert call_kwargs.kwargs["apartment_filters"] == {}


async def test_reset_updates_panel_keyboard() -> None:
    """After reset, panel is edited to show updated (empty) filters."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_reset

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {"city": "X"}})

    cb_data = FilterPanelCB(action="reset", field="")
    await on_filter_panel_reset(callback, state, cb_data)

    callback.message.edit_text.assert_called_once()


# --- on_filter_panel_back: close panel ---


async def test_back_deletes_panel_message() -> None:
    """Back deletes the inline panel message."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_back

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()

    cb_data = FilterPanelCB(action="back", field="")
    await on_filter_panel_back(callback, state, cb_data)

    callback.message.delete.assert_called_once()
    callback.answer.assert_called()


async def test_back_from_submenu_returns_to_panel() -> None:
    """Back from sub-menu (field != '') returns to main panel."""
    from telegram_bot.callback_data import FilterPanelCB
    from telegram_bot.handlers.filter_panel import on_filter_panel_back

    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {"city": "Несебр"}})

    cb_data = FilterPanelCB(action="back", field="city")
    await on_filter_panel_back(callback, state, cb_data)

    # Should edit message back to main panel (not delete)
    callback.message.edit_text.assert_called_once()
    callback.message.delete.assert_not_called()
    callback.answer.assert_called()
