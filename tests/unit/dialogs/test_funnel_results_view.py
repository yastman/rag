"""Tests for funnel results list view (restored, #935-#936)."""

from __future__ import annotations


def test_results_window_exists_in_dialog():
    """Funnel dialog must have a results Window."""
    from telegram_bot.dialogs.funnel import funnel_dialog
    from telegram_bot.dialogs.states import FunnelSG

    states = [w.get_state() for w in funnel_dialog.windows.values()]
    assert FunnelSG.results in states


def test_results_window_has_html_parse_mode():
    """Results window must use HTML parse mode for bold formatting."""
    from aiogram.enums import ParseMode

    from telegram_bot.dialogs.funnel import funnel_dialog
    from telegram_bot.dialogs.states import FunnelSG

    window = funnel_dialog.windows[FunnelSG.results]
    assert window.parse_mode == ParseMode.HTML


def test_get_results_data_exported():
    """get_results_data must be exported from funnel module."""
    import telegram_bot.dialogs.funnel as m

    assert hasattr(m, "get_results_data"), "get_results_data must exist"


def test_on_search_list_exported():
    """on_search_list must be exported from funnel module."""
    import telegram_bot.dialogs.funnel as m

    assert hasattr(m, "on_search_list"), "on_search_list must exist"
