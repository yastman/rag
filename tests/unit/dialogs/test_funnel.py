"""Tests for BANT funnel dialog."""

from telegram_bot.dialogs.funnel import funnel_dialog
from telegram_bot.dialogs.states import FunnelSG


def test_funnel_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(funnel_dialog, Dialog)


def test_funnel_has_all_windows():
    windows = funnel_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FunnelSG.property_type in states
    assert FunnelSG.budget in states
    assert FunnelSG.timeline in states
    assert FunnelSG.results in states
