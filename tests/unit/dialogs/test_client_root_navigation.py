"""Tests for SDK-native client root navigation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def _iter_widgets(window):
    if hasattr(window, "keyboard") and window.keyboard is not None:
        yield from _iter_kbd_widgets(window.keyboard)


def _iter_kbd_widgets(widget):
    yield widget
    for child in getattr(widget, "buttons", ()):
        yield from _iter_kbd_widgets(child)
    for child in getattr(widget, "widgets", ()):
        yield from _iter_kbd_widgets(child)


async def test_root_menu_button_from_nested_flow_uses_reset_stack():
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.root_nav import on_back_to_main_menu
    from telegram_bot.dialogs.states import ClientMenuSG

    manager = AsyncMock()

    await on_back_to_main_menu(MagicMock(), MagicMock(), manager)

    manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)


def test_filter_dialog_contains_main_menu_button():
    from telegram_bot.dialogs.filter_dialog import filter_dialog

    button_ids = {
        getattr(widget, "widget_id", "")
        for window in filter_dialog.windows.values()
        for widget in _iter_widgets(window)
    }
    assert "main_menu" in button_ids
