"""Tests for SDK-native client root navigation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from aiogram_dialog.widgets.kbd import Cancel


def _iter_widgets(window):
    if hasattr(window, "keyboard") and window.keyboard is not None:
        yield from _iter_kbd_widgets(window.keyboard)


def _iter_kbd_widgets(widget):
    yield widget
    for child in getattr(widget, "buttons", ()):
        yield from _iter_kbd_widgets(child)
    for child in getattr(widget, "widgets", ()):
        yield from _iter_kbd_widgets(child)


async def test_root_menu_button_from_nested_flow_returns_to_reply_keyboard_root():
    from aiogram.types import ReplyKeyboardMarkup

    from telegram_bot.dialogs.root_nav import on_back_to_main_menu

    manager = AsyncMock()
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()

    await on_back_to_main_menu(callback, MagicMock(), manager)

    manager.reset_stack.assert_awaited_once_with(remove_keyboard=True)
    callback.message.answer.assert_called_once()
    _, kwargs = callback.message.answer.call_args
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)


def test_filter_dialog_contains_main_menu_button():
    from telegram_bot.dialogs.filter_dialog import filter_dialog

    button_ids = {
        getattr(widget, "widget_id", "")
        for window in filter_dialog.windows.values()
        for widget in _iter_widgets(window)
    }
    assert "main_menu" in button_ids


def test_reset_stack_roots_do_not_use_cancel_to_leave_root():
    from telegram_bot.dialogs.faq import faq_dialog
    from telegram_bot.dialogs.funnel import funnel_dialog
    from telegram_bot.dialogs.settings import settings_dialog
    from telegram_bot.dialogs.states import FaqSG, FunnelSG, SettingsSG

    windows = (
        faq_dialog.windows[FaqSG.main],
        settings_dialog.windows[SettingsSG.main],
        funnel_dialog.windows[FunnelSG.city],
    )

    for window in windows:
        widgets = list(_iter_widgets(window))
        assert not any(isinstance(widget, Cancel) for widget in widgets)
