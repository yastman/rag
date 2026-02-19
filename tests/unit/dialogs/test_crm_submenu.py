"""Tests for CRM submenu dialog."""

from telegram_bot.dialogs.crm_submenu import (
    _BUTTON_QUERIES,
    crm_submenu_dialog,
    get_crm_submenu_data,
)
from telegram_bot.dialogs.states import CrmSubmenuSG


def test_crm_submenu_dialog_exists():
    """CRM submenu dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(crm_submenu_dialog, Dialog)


def test_crm_submenu_has_main_window():
    """CRM submenu has window for CrmSubmenuSG.main state."""
    windows = crm_submenu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert CrmSubmenuSG.main in states


def test_crm_submenu_button_queries_defined():
    """All 5 action buttons have mapped query text (6th is Cancel/Back)."""
    expected_ids = {
        "crm_create_deal",
        "crm_create_contact",
        "crm_add_note",
        "crm_create_task",
        "crm_pipelines",
    }
    assert set(_BUTTON_QUERIES.keys()) == expected_ids
    for widget_id, query in _BUTTON_QUERIES.items():
        assert isinstance(query, str) and len(query) > 0, f"Empty query for {widget_id}"


async def test_crm_submenu_fallback_getter_has_required_keys():
    """Fallback getter (no i18n) returns all required text keys."""
    result = await get_crm_submenu_data()
    for key in (
        "title",
        "btn_create_deal",
        "btn_create_contact",
        "btn_add_note",
        "btn_create_task",
        "btn_pipelines",
        "btn_back",
    ):
        assert key in result, f"Missing key: {key}"


async def test_crm_submenu_i18n_getter_returns_all_keys():
    """Getter with i18n returns all button labels from FTL."""
    from unittest.mock import MagicMock

    i18n = MagicMock()
    i18n.get.side_effect = lambda key, **_: f"[{key}]"
    result = await get_crm_submenu_data(i18n=i18n)

    for key in (
        "title",
        "btn_create_deal",
        "btn_create_contact",
        "btn_add_note",
        "btn_create_task",
        "btn_pipelines",
        "btn_back",
    ):
        assert key in result
        assert result[key].startswith("[")
