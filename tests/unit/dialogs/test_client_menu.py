"""Tests for client menu dialog."""

from telegram_bot.dialogs.client_menu import _BUTTON_QUERIES, client_menu_dialog, get_menu_data
from telegram_bot.dialogs.states import ClientMenuSG, FunnelSG


def test_client_menu_dialog_exists():
    """Client menu dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(client_menu_dialog, Dialog)


def test_client_menu_has_main_window():
    """Client menu has window for ClientMenuSG.main state."""
    windows = client_menu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ClientMenuSG.main in states


def test_client_menu_button_queries_defined():
    """All action button widget_ids have mapped query text."""
    expected_ids = {"catalog", "favorites", "booking", "mortgage", "my_leads", "manager"}
    assert set(_BUTTON_QUERIES.keys()) == expected_ids
    for widget_id, query in _BUTTON_QUERIES.items():
        assert isinstance(query, str) and len(query) > 0, f"Empty query for {widget_id}"


async def test_client_menu_fallback_getter_has_9_keys():
    """Fallback getter (no i18n) returns all 9 button labels."""
    result = await get_menu_data()
    # greeting + 9 buttons
    assert "greeting" in result
    for key in (
        "btn_search",
        "btn_catalog",
        "btn_favorites",
        "btn_booking",
        "btn_mortgage",
        "btn_my_leads",
        "btn_faq",
        "btn_manager",
        "btn_settings",
    ):
        assert key in result, f"Missing key: {key}"


async def test_client_menu_i18n_getter_returns_all_keys():
    """Getter with i18n returns all 9 button labels from FTL."""
    from unittest.mock import MagicMock

    i18n = MagicMock()
    i18n.get.side_effect = lambda key, **_: f"[{key}]"
    result = await get_menu_data(i18n=i18n)

    for key in (
        "btn_search",
        "btn_catalog",
        "btn_favorites",
        "btn_booking",
        "btn_mortgage",
        "btn_my_leads",
        "btn_faq",
        "btn_manager",
        "btn_settings",
    ):
        assert key in result
        assert result[key].startswith("[")


def test_client_menu_launch_mode_root():
    """Client menu dialog uses LaunchMode.ROOT."""
    from aiogram_dialog import LaunchMode

    assert client_menu_dialog.launch_mode == LaunchMode.ROOT


def test_client_menu_search_starts_funnel_from_complex():
    """Search button must start funnel from the complex selection step (#697)."""
    window = client_menu_dialog.windows[ClientMenuSG.main]
    buttons = getattr(window.keyboard, "buttons", ())
    funnel_start = next((btn for btn in buttons if getattr(btn, "widget_id", "") == "funnel"), None)
    assert funnel_start is not None
    assert getattr(funnel_start, "state", None) == FunnelSG.city
