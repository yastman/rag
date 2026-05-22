"""Tests for CRM Contacts dialogs: CreateContactWizard, ContactsMenu, SearchContacts (#697)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


# --- ContactsMenuSG states ---


def test_contacts_menu_sg_has_main():
    """ContactsMenuSG.main state exists."""
    from telegram_bot.dialogs.states import ContactsMenuSG

    assert hasattr(ContactsMenuSG, "main")


# --- SearchContactsSG states ---


def test_search_contacts_sg_has_query_and_results():
    """SearchContactsSG has query and results states."""
    from telegram_bot.dialogs.states import SearchContactsSG

    assert hasattr(SearchContactsSG, "query")
    assert hasattr(SearchContactsSG, "results")


# --- Dialog objects ---


def test_contacts_menu_dialog_is_dialog():
    """contacts_menu_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_contacts import contacts_menu_dialog

    assert isinstance(contacts_menu_dialog, Dialog)


def test_contacts_menu_dialog_has_main_window():
    """contacts_menu_dialog has a window for ContactsMenuSG.main."""
    from telegram_bot.dialogs.crm_contacts import contacts_menu_dialog
    from telegram_bot.dialogs.states import ContactsMenuSG

    states = [w.get_state() for w in contacts_menu_dialog.windows.values()]
    assert ContactsMenuSG.main in states


def test_create_contact_dialog_is_dialog():
    """create_contact_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_contacts import create_contact_dialog

    assert isinstance(create_contact_dialog, Dialog)


def test_create_contact_dialog_has_all_wizard_windows():
    """create_contact_dialog has windows for all CreateContactSG states."""
    from telegram_bot.dialogs.crm_contacts import create_contact_dialog
    from telegram_bot.dialogs.states import CreateContactSG

    states = [w.get_state() for w in create_contact_dialog.windows.values()]
    for expected in (
        CreateContactSG.first_name,
        CreateContactSG.last_name,
        CreateContactSG.phone,
        CreateContactSG.email,
        CreateContactSG.summary,
    ):
        assert expected in states, f"Missing window for state: {expected}"


def test_search_contacts_dialog_is_dialog():
    """search_contacts_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_contacts import search_contacts_dialog

    assert isinstance(search_contacts_dialog, Dialog)


def test_search_contacts_dialog_has_query_and_results_windows():
    """search_contacts_dialog has windows for SearchContactsSG.query and .results."""
    from telegram_bot.dialogs.crm_contacts import search_contacts_dialog
    from telegram_bot.dialogs.states import SearchContactsSG

    states = [w.get_state() for w in search_contacts_dialog.windows.values()]
    assert SearchContactsSG.query in states
    assert SearchContactsSG.results in states


# --- Getters ---


async def test_get_contacts_menu_data_returns_required_keys():
    """Contacts menu getter returns title + button labels."""
    from telegram_bot.dialogs.crm_contacts import get_contacts_menu_data

    result = await get_contacts_menu_data()
    for key in ("title", "btn_create", "btn_search", "btn_back"):
        assert key in result, f"Missing key: {key}"
        assert isinstance(result[key], str) and len(result[key]) > 0, f"Empty value for {key}"


async def test_get_contact_first_name_prompt_returns_text():
    """First name prompt getter returns non-empty prompt."""
    from telegram_bot.dialogs.crm_contacts import get_contact_first_name_prompt

    result = await get_contact_first_name_prompt()
    assert "prompt" in result
    assert len(result["prompt"]) > 0


async def test_get_contact_summary_returns_preview():
    """Contact summary getter formats collected data into preview."""
    from telegram_bot.dialogs.crm_contacts import get_contact_summary_data

    dm = MagicMock()
    dm.dialog_data = {
        "first_name": "Ivan",
        "last_name": "Petrov",
        "phone": "+79001234567",
        "email": "ivan@example.com",
    }

    result = await get_contact_summary_data(dialog_manager=dm)
    assert "Ivan" in result["summary_text"]
    assert "Petrov" in result["summary_text"]
    assert "+79001234567" in result["summary_text"]


async def test_get_contact_summary_without_optional_fields():
    """Contact summary getter handles missing optional last_name, email."""
    from telegram_bot.dialogs.crm_contacts import get_contact_summary_data

    dm = MagicMock()
    dm.dialog_data = {"first_name": "Anna", "phone": "+79000000000"}

    result = await get_contact_summary_data(dialog_manager=dm)
    assert "Anna" in result["summary_text"]


async def test_get_search_contacts_results_empty_kommo():
    """Search contacts results getter handles missing kommo_client."""
    from telegram_bot.dialogs.crm_contacts import get_search_contacts_results

    dm = MagicMock()
    dm.dialog_data = {"search_query": "Ivan"}
    dm.middleware_data = {}

    result = await get_search_contacts_results(dialog_manager=dm)
    assert "results_text" in result


async def test_get_search_contacts_results_with_mock_kommo():
    """Search contacts results returns formatted cards from kommo."""
    from telegram_bot.dialogs.crm_contacts import get_search_contacts_results
    from telegram_bot.services.kommo_models import Contact

    fake_contact = Contact(id=7, first_name="Ivan", last_name="Petrov")

    kommo = AsyncMock()
    kommo.get_contacts = AsyncMock(return_value=[fake_contact])

    dm = MagicMock()
    dm.dialog_data = {"search_query": "Ivan"}
    dm.middleware_data = {"kommo_client": kommo}

    result = await get_search_contacts_results(dialog_manager=dm)
    assert "Ivan" in result["results_text"]


# --- Wizard step handlers ---


async def test_on_first_name_entered_saves_and_advances():
    """First name handler saves to dialog_data and switches to last_name."""
    from telegram_bot.dialogs.crm_contacts import on_first_name_entered
    from telegram_bot.dialogs.states import CreateContactSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    await on_first_name_entered(MagicMock(), MagicMock(), dm, "Ivan")

    assert dm.dialog_data["first_name"] == "Ivan"
    dm.switch_to.assert_called_once_with(CreateContactSG.last_name)


async def test_on_last_name_entered_saves_and_advances():
    """Last name handler saves and switches to phone."""
    from telegram_bot.dialogs.crm_contacts import on_last_name_entered
    from telegram_bot.dialogs.states import CreateContactSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    await on_last_name_entered(MagicMock(), MagicMock(), dm, "Petrov")

    assert dm.dialog_data["last_name"] == "Petrov"
    dm.switch_to.assert_called_once_with(CreateContactSG.phone)


async def test_on_phone_entered_saves_and_advances():
    """Phone handler saves and switches to email."""
    from telegram_bot.dialogs.crm_contacts import on_phone_entered
    from telegram_bot.dialogs.states import CreateContactSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    message.answer = AsyncMock()

    await on_phone_entered(message, MagicMock(), dm, "+79001234567")

    assert dm.dialog_data["phone"] == "+79001234567"
    dm.switch_to.assert_called_once_with(CreateContactSG.email)


async def test_on_email_entered_saves_and_advances_to_summary():
    """Email handler saves and switches to summary."""
    from telegram_bot.dialogs.crm_contacts import on_email_entered
    from telegram_bot.dialogs.states import CreateContactSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    await on_email_entered(MagicMock(), MagicMock(), dm, "ivan@test.com")

    assert dm.dialog_data["email"] == "ivan@test.com"
    dm.switch_to.assert_called_once_with(CreateContactSG.summary)


async def test_on_email_skip_advances_to_summary_without_email():
    """Email skip handler (empty/skip) advances to summary without saving email."""
    from telegram_bot.dialogs.crm_contacts import on_email_skip
    from telegram_bot.dialogs.states import CreateContactSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    callback = MagicMock()
    await on_email_skip(callback, MagicMock(), dm)

    assert dm.dialog_data.get("email") is None
    dm.switch_to.assert_called_once_with(CreateContactSG.summary)


# --- Contact confirm handler ---


async def test_on_contact_confirm_calls_upsert_contact():
    """Confirm handler calls kommo.upsert_contact() with correct data."""
    from telegram_bot.dialogs.crm_contacts import on_contact_confirm
    from telegram_bot.services.kommo_models import Contact

    created = Contact(id=200, first_name="Ivan", last_name="Petrov")
    kommo = AsyncMock()
    kommo.upsert_contact = AsyncMock(return_value=created)

    dm = MagicMock()
    dm.dialog_data = {
        "first_name": "Ivan",
        "last_name": "Petrov",
        "phone": "+79001234567",
        "email": "ivan@test.com",
    }
    dm.middleware_data = {"kommo_client": kommo}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    button = MagicMock()

    await on_contact_confirm(callback, button, dm)

    kommo.upsert_contact.assert_called_once()
    callback.message.answer.assert_called_once()
    dm.done.assert_called_once()


async def test_on_contact_confirm_no_kommo_shows_error():
    """Confirm handler shows error when kommo_client is None."""
    from telegram_bot.dialogs.crm_contacts import on_contact_confirm

    dm = MagicMock()
    dm.dialog_data = {"first_name": "Ivan", "phone": "+79001234567"}
    dm.middleware_data = {}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    button = MagicMock()

    await on_contact_confirm(callback, button, dm)

    callback.message.answer.assert_called_once()
    dm.done.assert_not_called()


# --- Search query handler ---


async def test_on_search_contacts_query_saves_and_switches():
    """Search query handler saves and switches to results."""
    from telegram_bot.dialogs.crm_contacts import on_search_contacts_query
    from telegram_bot.dialogs.states import SearchContactsSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    message.text = "Petrov"

    await on_search_contacts_query(message, MagicMock(), dm)

    assert dm.dialog_data["search_query"] == "Petrov"
    dm.switch_to.assert_called_once_with(SearchContactsSG.results)
