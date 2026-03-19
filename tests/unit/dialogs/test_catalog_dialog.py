"""Tests for the dialog-owned catalog shell."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.states import CatalogSG, ClientMenuSG, FilterSG


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
async def test_catalog_home_uses_reset_stack_to_client_root() -> None:
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.catalog import on_catalog_home

    manager = AsyncMock()
    await on_catalog_home(MagicMock(), MagicMock(), manager)

    manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)


@pytest.mark.asyncio
async def test_catalog_filters_starts_filter_dialog_with_current_filters() -> None:
    from aiogram_dialog import ShowMode, StartMode

    from telegram_bot.dialogs.catalog import on_catalog_filters

    state = AsyncMock()
    state.get_data.return_value = {"catalog_runtime": {"filters": {"city": "Варна"}}}
    manager = AsyncMock()
    manager.middleware_data = {"state": state}
    manager.done = AsyncMock()
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.delete = AsyncMock()

    await on_catalog_filters(callback, MagicMock(), manager)

    assert manager.show_mode == ShowMode.NO_UPDATE
    manager.done.assert_awaited_once()
    callback.message.delete.assert_awaited_once()
    manager.start.assert_awaited_once_with(
        FilterSG.hub,
        data={"filters": {"city": "Варна"}},
        mode=StartMode.RESET_STACK,
    )


@pytest.mark.asyncio
async def test_render_catalog_results_with_keyboard_list_mode_attaches_keyboard() -> None:
    from telegram_bot.dialogs.catalog_transport import render_catalog_results_with_keyboard

    message = MagicMock()
    message.answer = AsyncMock()

    await render_catalog_results_with_keyboard(
        message=message,
        property_bot=None,
        results=[{"id": "apt-1"}],
        total_count=12,
        view_mode="list",
        shown_start=1,
        shown_count=10,
        telegram_id=123,
    )

    reply_markup = message.answer.await_args.kwargs["reply_markup"]
    assert reply_markup is not None
