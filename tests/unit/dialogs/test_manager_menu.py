"""Tests for manager menu dialog."""

from telegram_bot.dialogs.manager_menu import (
    _BUTTON_QUERIES,
    get_manager_menu_data,
    manager_menu_dialog,
)
from telegram_bot.dialogs.states import ManagerMenuSG


def test_manager_menu_dialog_exists():
    """Manager menu dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(manager_menu_dialog, Dialog)


def test_manager_menu_has_main_window():
    """Manager menu has window for ManagerMenuSG.main state."""
    windows = manager_menu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ManagerMenuSG.main in states


def test_manager_menu_button_queries_defined():
    """All action button widget_ids have mapped query text."""
    expected_ids = {
        "mgr_deals",
        "mgr_contacts",
        "mgr_new_deal",
        "mgr_funnel_stats",
        "mgr_hot_leads",
        "mgr_tasks",
        "mgr_search",
    }
    assert set(_BUTTON_QUERIES.keys()) == expected_ids
    for widget_id, query in _BUTTON_QUERIES.items():
        assert isinstance(query, str) and len(query) > 0, f"Empty query for {widget_id}"


async def test_manager_menu_fallback_getter_has_9_keys():
    """Fallback getter (no i18n) returns all 9 button labels."""
    result = await get_manager_menu_data()
    assert "greeting" in result
    for key in (
        "btn_deals",
        "btn_contacts",
        "btn_new_deal",
        "btn_funnel_stats",
        "btn_hot_leads",
        "btn_tasks",
        "btn_crm",
        "btn_search",
        "btn_settings",
    ):
        assert key in result, f"Missing key: {key}"


async def test_manager_menu_i18n_getter_returns_all_keys():
    """Getter with i18n returns all 9 button labels from FTL."""
    from unittest.mock import MagicMock

    i18n = MagicMock()
    i18n.get.side_effect = lambda key, **_: f"[{key}]"
    result = await get_manager_menu_data(i18n=i18n)

    for key in (
        "btn_deals",
        "btn_contacts",
        "btn_new_deal",
        "btn_funnel_stats",
        "btn_hot_leads",
        "btn_tasks",
        "btn_crm",
        "btn_search",
        "btn_settings",
    ):
        assert key in result
        assert result[key].startswith("[")


def test_manager_menu_launch_mode_root():
    """Manager menu dialog uses LaunchMode.ROOT."""
    from aiogram_dialog import LaunchMode

    assert manager_menu_dialog.launch_mode == LaunchMode.ROOT
