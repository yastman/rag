"""Tests for the catalog state owner and reply-keyboard routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.states import CatalogSG, FilterSG


def test_catalog_dialog_has_results_window() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog

    assert CatalogSG.results in catalog_dialog.windows


def test_catalog_results_window_has_no_inline_control_buttons() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog

    window = catalog_dialog.windows[CatalogSG.results]
    widget_ids = {getattr(widget, "widget_id", None) for widget in window.keyboard.buttons}
    assert "catalog_more" not in widget_ids
    assert "catalog_filters" not in widget_ids
    assert "catalog_home" not in widget_ids


def test_catalog_results_window_keeps_message_input() -> None:
    from aiogram_dialog.widgets.input import MessageInput

    from telegram_bot.dialogs.catalog import catalog_dialog

    window = catalog_dialog.windows[CatalogSG.results]
    assert any(isinstance(widget, MessageInput) for widget in window.on_message.inputs)


@pytest.mark.asyncio
async def test_catalog_home_restores_client_reply_keyboard() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_home

    manager = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    manager.middleware_data = {"state": state, "i18n": None}
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock(id=456)
    callback.message.bot = MagicMock(delete_message=AsyncMock())
    callback.message.from_user = MagicMock(first_name="Test")

    await on_catalog_home(callback, MagicMock(), manager)

    manager.done.assert_awaited_once()
    callback.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_catalog_filters_starts_filter_dialog_with_current_filters() -> None:
    from aiogram.types import ReplyKeyboardRemove
    from aiogram_dialog import ShowMode, StartMode

    from telegram_bot.dialogs.catalog import on_catalog_filters

    state = AsyncMock()
    state.get_data.return_value = {"catalog_runtime": {"filters": {"city": "Варна"}}}
    manager = AsyncMock()
    manager.middleware_data = {"state": state}
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    callback.message.chat = MagicMock(id=456)
    callback.message.bot = MagicMock(delete_message=AsyncMock())

    await on_catalog_filters(callback, MagicMock(), manager)

    callback.message.answer.assert_awaited()
    reply_markup = callback.message.answer.await_args.kwargs["reply_markup"]
    assert isinstance(reply_markup, ReplyKeyboardRemove)
    manager.start.assert_awaited_once_with(
        FilterSG.hub,
        data={"filters": {"city": "Варна"}},
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.SEND,
    )


@pytest.mark.asyncio
async def test_show_catalog_controls_skips_status_message_for_list_mode() -> None:
    from telegram_bot.dialogs.catalog import show_catalog_controls

    manager = AsyncMock()
    state = AsyncMock()
    state.get_data.return_value = {}
    manager.middleware_data = {"state": state, "i18n": None}
    message = MagicMock()
    message.answer = AsyncMock()
    message.chat = MagicMock(id=456)
    message.bot = MagicMock(delete_message=AsyncMock())

    runtime = {
        "view_mode": "list",
        "shown_count": 5,
        "total": 5,
        "query": "funnel:Солнечный берег",
        "source": "funnel",
    }

    updated = await show_catalog_controls(message=message, dialog_manager=manager, runtime=runtime)

    assert updated["view_mode"] == "list"
    message.answer.assert_not_awaited()
