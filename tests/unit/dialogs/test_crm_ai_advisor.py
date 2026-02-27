"""Tests for CRM AI Advisor dialog (#697)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


# --- Module imports ---


def test_crm_ai_advisor_module_is_importable():
    """crm_ai_advisor module can be imported."""
    from telegram_bot.dialogs import crm_ai_advisor  # noqa: F401


def test_advisor_dialog_is_exported():
    """advisor_dialog is exported from crm_ai_advisor module."""
    from telegram_bot.dialogs.crm_ai_advisor import advisor_dialog

    assert advisor_dialog is not None


def test_advisor_dialog_is_aiogram_dialog():
    """advisor_dialog is an aiogram_dialog Dialog instance."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_ai_advisor import advisor_dialog

    assert isinstance(advisor_dialog, Dialog)


# --- FSM States ---


def test_ai_advisor_sg_has_result_state():
    """AIAdvisorSG has 'result' state for displaying LLM output."""
    from telegram_bot.dialogs.states import AIAdvisorSG

    assert hasattr(AIAdvisorSG, "result"), "AIAdvisorSG must have 'result' state"


def test_ai_advisor_sg_has_main_state():
    """AIAdvisorSG has 'main' state (navigation menu)."""
    from telegram_bot.dialogs.states import AIAdvisorSG

    assert hasattr(AIAdvisorSG, "main")


# --- Action getter ---


async def test_get_advisor_menu_returns_dict_with_title_and_items():
    """get_advisor_menu getter returns dict with 'title' and 'items'."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_menu

    result = await get_advisor_menu()

    assert "title" in result
    assert "items" in result
    assert isinstance(result["items"], list)
    assert len(result["items"]) > 0


async def test_get_advisor_menu_items_have_two_elements():
    """Each item in advisor menu is a (label, action_id) tuple."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_menu

    result = await get_advisor_menu()

    for item in result["items"]:
        assert len(item) == 2, f"Item must be (label, id) pair: {item}"


async def test_get_advisor_menu_has_leads_action():
    """Advisor menu has 'leads' action."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_menu

    result = await get_advisor_menu()
    action_ids = [item[1] for item in result["items"]]
    assert "leads" in action_ids


async def test_get_advisor_menu_has_tasks_action():
    """Advisor menu has 'tasks' action."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_menu

    result = await get_advisor_menu()
    action_ids = [item[1] for item in result["items"]]
    assert "tasks" in action_ids


async def test_get_advisor_menu_has_stale_action():
    """Advisor menu has 'stale' action for stale deals."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_menu

    result = await get_advisor_menu()
    action_ids = [item[1] for item in result["items"]]
    assert "stale" in action_ids


async def test_get_advisor_menu_has_briefing_action():
    """Advisor menu has 'briefing' action for full briefing."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_menu

    result = await get_advisor_menu()
    action_ids = [item[1] for item in result["items"]]
    assert "briefing" in action_ids


# --- on_advisor_action handler ---


async def test_on_advisor_action_sets_dialog_data():
    """on_advisor_action stores action in dialog_manager.dialog_data."""
    from telegram_bot.dialogs.crm_ai_advisor import on_advisor_action
    from telegram_bot.dialogs.states import AIAdvisorSG

    callback = MagicMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}
    manager.switch_to = AsyncMock()

    await on_advisor_action(callback, widget, manager, "leads")

    assert manager.dialog_data["advisor_action"] == "leads"
    manager.switch_to.assert_called_once_with(AIAdvisorSG.result)


async def test_on_advisor_action_switches_to_result_state():
    """on_advisor_action switches dialog to result state."""
    from telegram_bot.dialogs.crm_ai_advisor import on_advisor_action
    from telegram_bot.dialogs.states import AIAdvisorSG

    callback = MagicMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}
    manager.switch_to = AsyncMock()

    await on_advisor_action(callback, widget, manager, "briefing")

    manager.switch_to.assert_called_once_with(AIAdvisorSG.result)


# --- get_advisor_result getter ---


async def test_get_advisor_result_returns_error_when_no_service():
    """get_advisor_result returns error message when ai_advisor_service is not in middleware."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"advisor_action": "leads"}
    dialog_manager.middleware_data = {}  # No advisor service

    result = await get_advisor_result(dialog_manager=dialog_manager)

    assert "result_text" in result
    assert isinstance(result["result_text"], str)
    assert len(result["result_text"]) > 0


async def test_get_advisor_result_calls_get_prioritized_leads():
    """get_advisor_result calls advisor.get_prioritized_leads for 'leads' action."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    advisor = MagicMock()
    advisor.get_prioritized_leads = AsyncMock(return_value="Лиды приоритизированы")

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"advisor_action": "leads"}
    dialog_manager.middleware_data = {"ai_advisor_service": advisor}

    result = await get_advisor_result(dialog_manager=dialog_manager)

    advisor.get_prioritized_leads.assert_called_once()
    assert result["result_text"] == "Лиды приоритизированы"


async def test_get_advisor_result_calls_get_prioritized_tasks():
    """get_advisor_result calls advisor.get_prioritized_tasks for 'tasks' action."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    advisor = MagicMock()
    advisor.get_prioritized_tasks = AsyncMock(return_value="Задачи приоритизированы")

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"advisor_action": "tasks"}
    dialog_manager.middleware_data = {"ai_advisor_service": advisor}

    result = await get_advisor_result(dialog_manager=dialog_manager)

    advisor.get_prioritized_tasks.assert_called_once()
    assert result["result_text"] == "Задачи приоритизированы"


async def test_get_advisor_result_calls_get_stale_deals():
    """get_advisor_result calls advisor.get_stale_deals for 'stale' action."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    advisor = MagicMock()
    advisor.get_stale_deals = AsyncMock(return_value="Застрявшие сделки")

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"advisor_action": "stale"}
    dialog_manager.middleware_data = {"ai_advisor_service": advisor}

    result = await get_advisor_result(dialog_manager=dialog_manager)

    advisor.get_stale_deals.assert_called_once()
    assert result["result_text"] == "Застрявшие сделки"


async def test_get_advisor_result_calls_get_full_briefing():
    """get_advisor_result calls advisor.get_full_briefing for 'briefing' action."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    advisor = MagicMock()
    advisor.get_full_briefing = AsyncMock(return_value="Полный брифинг")

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"advisor_action": "briefing"}
    dialog_manager.middleware_data = {"ai_advisor_service": advisor}

    result = await get_advisor_result(dialog_manager=dialog_manager)

    advisor.get_full_briefing.assert_called_once()
    assert result["result_text"] == "Полный брифинг"


async def test_get_advisor_result_handles_exception_gracefully():
    """get_advisor_result returns error text when advisor raises exception."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    advisor = MagicMock()
    advisor.get_prioritized_leads = AsyncMock(side_effect=Exception("Service unavailable"))

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"advisor_action": "leads"}
    dialog_manager.middleware_data = {"ai_advisor_service": advisor}

    result = await get_advisor_result(dialog_manager=dialog_manager)

    assert "result_text" in result
    assert "❌" in result["result_text"] or "ошибка" in result["result_text"].lower()


async def test_get_advisor_result_returns_dash_when_no_dialog_manager():
    """get_advisor_result returns safe default when dialog_manager is None."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    result = await get_advisor_result(dialog_manager=None)

    assert "result_text" in result
    assert isinstance(result["result_text"], str)


# --- on_advisor_back handler ---


async def test_on_advisor_back_switches_to_main():
    """on_advisor_back switches dialog back to main state."""
    from telegram_bot.dialogs.crm_ai_advisor import on_advisor_back
    from telegram_bot.dialogs.states import AIAdvisorSG

    callback = MagicMock()
    button = MagicMock()
    manager = MagicMock()
    manager.switch_to = AsyncMock()

    await on_advisor_back(callback, button, manager)

    manager.switch_to.assert_called_once_with(AIAdvisorSG.main)
