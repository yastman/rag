"""Tests for CRM navigation hub dialog (#697)."""

from telegram_bot.dialogs.crm_submenu import (
    crm_submenu_dialog,
    get_crm_menu_data,
)
from telegram_bot.dialogs.states import CRMMenuSG


def test_crm_submenu_dialog_exists():
    """CRM hub dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(crm_submenu_dialog, Dialog)


def test_crm_submenu_has_main_window():
    """CRM hub dialog has window for CRMMenuSG.main state."""
    windows = crm_submenu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert CRMMenuSG.main in states


async def test_crm_menu_getter_has_required_keys():
    """Getter returns all required navigation button keys."""
    result = await get_crm_menu_data()
    for key in (
        "title",
        "btn_leads",
        "btn_contacts",
        "btn_tasks",
        "btn_note",
        "btn_ai_advisor",
        "btn_settings",
        "btn_back",
    ):
        assert key in result, f"Missing key: {key}"
        assert isinstance(result[key], str) and len(result[key]) > 0, f"Empty value for {key}"
