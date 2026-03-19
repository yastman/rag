"""Tests for client menu dialog."""

from telegram_bot.dialogs.client_menu import _DIRECT_ACTIONS, client_menu_dialog, get_menu_data
from telegram_bot.dialogs.states import ClientMenuSG, FunnelSG, ViewingSG


def test_client_menu_dialog_exists():
    """Client menu dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(client_menu_dialog, Dialog)


def test_client_menu_has_main_window():
    """Client menu has window for ClientMenuSG.main state."""
    windows = client_menu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ClientMenuSG.main in states


def _iter_widgets(widget):
    yield widget
    for child in getattr(widget, "buttons", ()):
        yield from _iter_widgets(child)
    for child in getattr(widget, "widgets", ()):
        yield from _iter_widgets(child)


def test_client_menu_direct_actions_defined():
    """Direct-action buttons mirror the legacy root menu actions."""
    assert {"services", "ask", "bookmarks", "demo"} == _DIRECT_ACTIONS


async def test_client_menu_fallback_getter_has_7_keys():
    """Fallback getter (no i18n) returns the legacy 7-button labels."""
    result = await get_menu_data()
    for key in (
        "btn_search",
        "btn_services",
        "btn_viewing",
        "btn_manager",
        "btn_ask",
        "btn_bookmarks",
        "btn_demo",
    ):
        assert key in result, f"Missing key: {key}"


async def test_client_menu_i18n_getter_returns_all_keys():
    """Getter with i18n returns all 7 button labels from FTL."""
    from unittest.mock import MagicMock

    i18n = MagicMock()
    i18n.get.side_effect = lambda key, **_: f"[{key}]"
    result = await get_menu_data(i18n=i18n)

    for key in (
        "btn_search",
        "btn_services",
        "btn_viewing",
        "btn_manager",
        "btn_ask",
        "btn_bookmarks",
        "btn_demo",
    ):
        assert key in result
        assert result[key].startswith("[")


def test_client_menu_launch_mode_root():
    """Client menu dialog uses LaunchMode.ROOT."""
    from aiogram_dialog import LaunchMode

    assert client_menu_dialog.launch_mode == LaunchMode.ROOT


def test_client_menu_search_starts_funnel_from_city():
    """Search button must start funnel from the city selection step."""
    from aiogram_dialog import StartMode

    window = client_menu_dialog.windows[ClientMenuSG.main]
    buttons = {
        getattr(btn, "widget_id", ""): btn
        for btn in _iter_widgets(getattr(window, "keyboard", None))
    }
    funnel_start = buttons["funnel"]
    assert funnel_start is not None
    assert getattr(funnel_start, "state", None) == FunnelSG.city
    assert getattr(funnel_start, "mode", None) == StartMode.RESET_STACK


def test_client_menu_sdk_starts_use_reset_stack():
    """Search and viewing root starts should reset stale dialog stack."""
    from aiogram_dialog import StartMode

    window = client_menu_dialog.windows[ClientMenuSG.main]
    buttons = {
        getattr(btn, "widget_id", ""): btn
        for btn in _iter_widgets(getattr(window, "keyboard", None))
    }

    assert getattr(buttons["funnel"], "mode", None) == StartMode.RESET_STACK
    assert getattr(buttons["viewing"], "mode", None) == StartMode.RESET_STACK
    assert getattr(buttons["viewing"], "state", None) == ViewingSG.date


def test_client_menu_uses_legacy_2x3_plus_1_layout():
    """Start menu should keep the legacy 2x3 grid plus a full-width final row."""
    window = client_menu_dialog.windows[ClientMenuSG.main]
    rows = getattr(window.keyboard, "buttons", ())
    assert len(rows) == 2
    assert getattr(rows[0], "width", None) == 2

    top_group_ids = [getattr(btn, "widget_id", "") for btn in getattr(rows[0], "buttons", ())]
    assert top_group_ids == ["funnel", "services", "viewing", "manager", "ask", "bookmarks"]
    assert getattr(rows[1], "widget_id", "") == "demo"
