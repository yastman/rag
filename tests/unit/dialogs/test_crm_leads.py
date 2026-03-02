"""Tests for CRM Leads dialogs: CreateLeadWizard, LeadsMenu, MyLeads, SearchLeads (#697)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


# --- LeadsMenuSG states ---


def test_leads_menu_sg_has_main():
    """LeadsMenuSG.main state exists."""
    from telegram_bot.dialogs.states import LeadsMenuSG

    assert hasattr(LeadsMenuSG, "main")


# --- MyLeadsSG states ---


def test_my_leads_sg_has_main():
    """MyLeadsSG.main state exists."""
    from telegram_bot.dialogs.states import MyLeadsSG

    assert hasattr(MyLeadsSG, "main")


# --- SearchLeadsSG states ---


def test_search_leads_sg_has_query_and_results():
    """SearchLeadsSG has query and results states."""
    from telegram_bot.dialogs.states import SearchLeadsSG

    assert hasattr(SearchLeadsSG, "query")
    assert hasattr(SearchLeadsSG, "results")


# --- Dialog objects ---


def test_leads_menu_dialog_is_dialog():
    """leads_menu_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_leads import leads_menu_dialog

    assert isinstance(leads_menu_dialog, Dialog)


def test_leads_menu_dialog_has_main_window():
    """leads_menu_dialog has a window for LeadsMenuSG.main."""
    from telegram_bot.dialogs.crm_leads import leads_menu_dialog
    from telegram_bot.dialogs.states import LeadsMenuSG

    states = [w.get_state() for w in leads_menu_dialog.windows.values()]
    assert LeadsMenuSG.main in states


def test_create_lead_dialog_is_dialog():
    """create_lead_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_leads import create_lead_dialog

    assert isinstance(create_lead_dialog, Dialog)


def test_create_lead_dialog_has_all_wizard_windows():
    """create_lead_dialog has windows for all CreateLeadSG states."""
    from telegram_bot.dialogs.crm_leads import create_lead_dialog
    from telegram_bot.dialogs.states import CreateLeadSG

    states = [w.get_state() for w in create_lead_dialog.windows.values()]
    for expected in (
        CreateLeadSG.name,
        CreateLeadSG.budget,
        CreateLeadSG.pipeline,
        CreateLeadSG.summary,
    ):
        assert expected in states, f"Missing window for state: {expected}"


def test_my_leads_dialog_is_dialog():
    """my_leads_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_leads import my_leads_dialog

    assert isinstance(my_leads_dialog, Dialog)


def test_my_leads_dialog_has_main_window():
    """my_leads_dialog has a window for MyLeadsSG.main."""
    from telegram_bot.dialogs.crm_leads import my_leads_dialog
    from telegram_bot.dialogs.states import MyLeadsSG

    states = [w.get_state() for w in my_leads_dialog.windows.values()]
    assert MyLeadsSG.main in states


def test_search_leads_dialog_is_dialog():
    """search_leads_dialog is a valid aiogram-dialog Dialog."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_leads import search_leads_dialog

    assert isinstance(search_leads_dialog, Dialog)


def test_search_leads_dialog_has_query_and_results_windows():
    """search_leads_dialog has windows for SearchLeadsSG.query and .results."""
    from telegram_bot.dialogs.crm_leads import search_leads_dialog
    from telegram_bot.dialogs.states import SearchLeadsSG

    states = [w.get_state() for w in search_leads_dialog.windows.values()]
    assert SearchLeadsSG.query in states
    assert SearchLeadsSG.results in states


# --- Getters ---


async def test_get_leads_menu_data_returns_required_keys():
    """Leads menu getter returns title + button labels (no btn_search after #731)."""
    from telegram_bot.dialogs.crm_leads import get_leads_menu_data

    result = await get_leads_menu_data()
    for key in ("title", "btn_create", "btn_my_leads", "btn_back"):
        assert key in result, f"Missing key: {key}"
        assert isinstance(result[key], str) and len(result[key]) > 0, f"Empty value for {key}"


async def test_get_lead_name_prompt_returns_text():
    """Lead name prompt getter returns non-empty prompt text."""
    from telegram_bot.dialogs.crm_leads import get_lead_name_prompt

    result = await get_lead_name_prompt()
    assert "prompt" in result
    assert len(result["prompt"]) > 0


async def test_get_lead_budget_prompt_returns_text():
    """Lead budget prompt getter returns prompt with back button label."""
    from telegram_bot.dialogs.crm_leads import get_lead_budget_prompt

    result = await get_lead_budget_prompt()
    assert "prompt" in result
    assert "btn_back" in result


async def test_get_lead_summary_returns_preview_data():
    """Lead summary getter returns filled preview from dialog_data."""
    from telegram_bot.dialogs.crm_leads import get_lead_summary_data

    dm = MagicMock()
    dm.dialog_data = {
        "name": "Test Deal",
        "budget": 50000,
        "pipeline_id": 1,
        "pipeline_name": "Pipeline A",
    }

    result = await get_lead_summary_data(dialog_manager=dm)
    assert "Test Deal" in result["summary_text"]
    assert "50" in result["summary_text"] or "50000" in result["summary_text"]


async def test_get_lead_summary_without_budget():
    """Lead summary getter handles missing budget gracefully."""
    from telegram_bot.dialogs.crm_leads import get_lead_summary_data

    dm = MagicMock()
    dm.dialog_data = {"name": "No Budget Deal"}

    result = await get_lead_summary_data(dialog_manager=dm)
    assert "No Budget Deal" in result["summary_text"]


async def test_get_my_leads_no_kommo_client():
    """My leads getter returns empty state when kommo_client is absent."""
    from telegram_bot.dialogs.crm_leads import get_my_leads_data

    dm = MagicMock()
    dm.dialog_data = {}
    dm.middleware_data = {}
    dm.event = MagicMock()
    dm.event.from_user = MagicMock()
    dm.event.from_user.id = 12345

    result = await get_my_leads_data(dialog_manager=dm)
    assert "leads_text" in result
    assert "has_prev" in result
    assert "has_next" in result


async def test_get_my_leads_with_mock_kommo_client():
    """My leads getter formats lead cards from kommo_client response."""
    from telegram_bot.dialogs.crm_leads import get_my_leads_data
    from telegram_bot.services.kommo_models import Lead

    fake_lead = Lead(id=10, name="Deal Alpha", budget=75000)

    kommo = AsyncMock()
    kommo.search_leads = AsyncMock(return_value=[fake_lead])
    kommo.get_tasks = AsyncMock(return_value=[])

    dm = MagicMock()
    dm.dialog_data = {}
    dm.middleware_data = {"kommo_client": kommo}
    dm.event = MagicMock()
    dm.event.from_user = MagicMock()
    dm.event.from_user.id = 99

    result = await get_my_leads_data(dialog_manager=dm)
    assert "Deal Alpha" in result["leads_text"]


async def test_get_search_leads_results_empty():
    """Search leads results getter handles empty kommo_client."""
    from telegram_bot.dialogs.crm_leads import get_search_leads_results

    dm = MagicMock()
    dm.dialog_data = {"search_query": "test"}
    dm.middleware_data = {}

    result = await get_search_leads_results(dialog_manager=dm)
    assert "results_text" in result


async def test_get_search_leads_results_with_mock_kommo():
    """Search leads results returns formatted cards from kommo."""
    from telegram_bot.dialogs.crm_leads import get_search_leads_results
    from telegram_bot.services.kommo_models import Lead

    fake_lead = Lead(id=5, name="Searched Deal", budget=30000)

    kommo = AsyncMock()
    kommo.search_leads = AsyncMock(return_value=[fake_lead])

    dm = MagicMock()
    dm.dialog_data = {"search_query": "searched"}
    dm.middleware_data = {"kommo_client": kommo}

    result = await get_search_leads_results(dialog_manager=dm)
    assert "Searched Deal" in result["results_text"]


# --- on_name_entered handler ---


async def test_on_lead_name_entered_saves_name_and_advances():
    """Handler saves name to dialog_data and switches to budget state."""
    from telegram_bot.dialogs.crm_leads import on_lead_name_entered
    from telegram_bot.dialogs.states import CreateLeadSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    widget = MagicMock()

    await on_lead_name_entered(message, widget, dm, "My New Deal")

    assert dm.dialog_data["name"] == "My New Deal"
    dm.switch_to.assert_called_once_with(CreateLeadSG.budget)


# --- on_budget_entered handler ---


async def test_on_lead_budget_entered_valid_saves_and_advances():
    """Handler saves valid integer budget and switches to pipeline state."""
    from telegram_bot.dialogs.crm_leads import on_lead_budget_entered
    from telegram_bot.dialogs.states import CreateLeadSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    message.answer = AsyncMock()
    widget = MagicMock()

    await on_lead_budget_entered(message, widget, dm, "75000")

    assert dm.dialog_data["budget"] == 75000
    dm.switch_to.assert_called_once_with(CreateLeadSG.pipeline)


async def test_on_lead_budget_entered_skip_saves_none_and_advances():
    """Handler treats '0' or 'skip' as no budget and advances."""
    from telegram_bot.dialogs.crm_leads import on_lead_budget_entered
    from telegram_bot.dialogs.states import CreateLeadSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    message.answer = AsyncMock()
    widget = MagicMock()

    await on_lead_budget_entered(message, widget, dm, "0")
    dm.switch_to.assert_called_with(CreateLeadSG.pipeline)


async def test_on_lead_budget_entered_invalid_shows_error():
    """Handler shows error message for non-numeric budget."""
    from telegram_bot.dialogs.crm_leads import on_lead_budget_entered

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    message.answer = AsyncMock()
    widget = MagicMock()

    await on_lead_budget_entered(message, widget, dm, "not_a_number")

    message.answer.assert_called_once()
    dm.switch_to.assert_not_called()


# --- on_pipeline_selected handler ---


async def test_on_pipeline_selected_saves_and_advances():
    """Pipeline selection saves id+name and switches to summary."""
    from telegram_bot.dialogs.crm_leads import on_pipeline_selected
    from telegram_bot.dialogs.states import CreateLeadSG

    dm = MagicMock()
    dm.dialog_data = {"_pipelines": [["Pipeline A", "10"], ["Pipeline B", "20"]]}
    dm.switch_to = AsyncMock()

    callback = MagicMock()
    widget = MagicMock()

    await on_pipeline_selected(callback, widget, dm, "10")

    assert dm.dialog_data["pipeline_id"] == 10
    assert dm.dialog_data["pipeline_name"] == "Pipeline A"
    dm.switch_to.assert_called_once_with(CreateLeadSG.summary)


# --- on_lead_confirm handler (calls kommo API) ---


async def test_on_lead_confirm_calls_create_lead():
    """Confirm handler calls kommo.create_lead() with correct data."""
    from telegram_bot.dialogs.crm_leads import on_lead_confirm
    from telegram_bot.services.kommo_models import Lead

    created = Lead(id=100, name="New Deal", budget=50000)
    kommo = AsyncMock()
    kommo.create_lead = AsyncMock(return_value=created)

    dm = MagicMock()
    dm.dialog_data = {"name": "New Deal", "budget": 50000, "pipeline_id": 1}
    dm.middleware_data = {"kommo_client": kommo}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    button = MagicMock()

    await on_lead_confirm(callback, button, dm)

    kommo.create_lead.assert_called_once()
    callback.message.answer.assert_called_once()
    dm.done.assert_called_once()


async def test_on_lead_confirm_no_kommo_shows_error():
    """Confirm handler shows error when kommo_client is None."""
    from telegram_bot.dialogs.crm_leads import on_lead_confirm

    dm = MagicMock()
    dm.dialog_data = {"name": "Deal", "budget": 0}
    dm.middleware_data = {}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    button = MagicMock()

    await on_lead_confirm(callback, button, dm)

    callback.message.answer.assert_called_once()
    dm.done.assert_not_called()


# --- Search flow handler ---


async def test_on_search_leads_query_saves_and_switches():
    """Search query handler saves query and switches to results state."""
    from telegram_bot.dialogs.crm_leads import on_search_leads_query
    from telegram_bot.dialogs.states import SearchLeadsSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    message.text = "Ivanov"

    await on_search_leads_query(message, MagicMock(), dm)

    assert dm.dialog_data["search_query"] == "Ivanov"
    dm.switch_to.assert_called_once_with(SearchLeadsSG.results)


# ─────────────────────────────────────────────────────────────────────────────
# Task 3: Search button removed from leads menu (#731)
# ─────────────────────────────────────────────────────────────────────────────


async def test_leads_menu_getter_has_no_btn_search():
    """leads menu getter should not return btn_search after removal (#731)."""
    from telegram_bot.dialogs.crm_leads import get_leads_menu_data

    result = await get_leads_menu_data()
    assert "btn_search" not in result


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: Updated lead card — contact name, task count, no raw IDs (#731)
# ─────────────────────────────────────────────────────────────────────────────


def test_lead_card_no_raw_ids():
    """format_lead_card should not show raw status_id or pipeline_id (#731)."""
    from telegram_bot.dialogs.crm_cards import format_lead_card
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Test", budget=50000, status_id=123, pipeline_id=456)
    text, _ = format_lead_card(lead)
    assert "Статус ID" not in text
    assert "Pipeline ID" not in text


def test_lead_card_shows_contact_name():
    """format_lead_card displays contact name when contacts available (#731)."""
    from telegram_bot.dialogs.crm_cards import format_lead_card
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Test", budget=50000, contacts=[{"id": 10, "name": "Иван Петров"}])
    text, _ = format_lead_card(lead)
    assert "Иван Петров" in text


def test_lead_card_shows_task_count():
    """format_lead_card displays task_count when provided (#731)."""
    from telegram_bot.dialogs.crm_cards import format_lead_card
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Test", budget=50000)
    text, _ = format_lead_card(lead, task_count=3)
    assert "3" in text


def test_lead_card_shows_zero_tasks_by_default():
    """format_lead_card shows 0 tasks when task_count not provided (#731)."""
    from telegram_bot.dialogs.crm_cards import format_lead_card
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Test")
    text, _ = format_lead_card(lead)
    assert "Задач" in text


async def test_get_my_leads_batches_task_counts():
    """my leads getter fetches task counts and passes them to card formatter (#731)."""
    from telegram_bot.dialogs.crm_leads import get_my_leads_data
    from telegram_bot.services.kommo_models import Lead, Task

    fake_lead = Lead(id=10, name="Deal Beta", budget=20000)
    fake_task = Task(id=1, text="Call", entity_id=10, is_completed=False)

    kommo = AsyncMock()
    kommo.search_leads = AsyncMock(return_value=[fake_lead])
    kommo.get_tasks = AsyncMock(return_value=[fake_task])

    dm = MagicMock()
    dm.dialog_data = {}
    dm.middleware_data = {"kommo_client": kommo}

    result = await get_my_leads_data(dialog_manager=dm)
    # get_tasks should be called for task counts
    kommo.get_tasks.assert_called_once()
    assert "Deal Beta" in result["leads_text"]
