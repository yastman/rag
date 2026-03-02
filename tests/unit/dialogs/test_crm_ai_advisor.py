"""Tests for CRM AI Advisor dialog — redesigned with 2 buttons and loading state (#731)."""

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


def test_ai_advisor_sg_has_main_state():
    """AIAdvisorSG has 'main' state (navigation menu)."""
    from telegram_bot.dialogs.states import AIAdvisorSG

    assert hasattr(AIAdvisorSG, "main")


def test_ai_advisor_sg_has_loading_state():
    """AIAdvisorSG must have 'loading' state for showing LLM in progress."""
    from telegram_bot.dialogs.states import AIAdvisorSG

    assert hasattr(AIAdvisorSG, "loading"), "AIAdvisorSG must have 'loading' state"


def test_ai_advisor_sg_has_result_state():
    """AIAdvisorSG has 'result' state for displaying LLM output."""
    from telegram_bot.dialogs.states import AIAdvisorSG

    assert hasattr(AIAdvisorSG, "result"), "AIAdvisorSG must have 'result' state"


# --- Actions list ---


def test_advisor_has_exactly_two_actions():
    """Advisor should have exactly 2 action buttons: daily_plan and deal_tips."""
    from telegram_bot.dialogs.crm_ai_advisor import _ADVISOR_ACTIONS

    assert len(_ADVISOR_ACTIONS) == 2


def test_advisor_actions_are_daily_plan_and_deal_tips():
    """Advisor action IDs should be 'daily_plan' and 'deal_tips'."""
    from telegram_bot.dialogs.crm_ai_advisor import _ADVISOR_ACTIONS

    action_ids = [a[1] for a in _ADVISOR_ACTIONS]
    assert "daily_plan" in action_ids
    assert "deal_tips" in action_ids


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


# --- Loading window getter ---


async def test_get_loading_data_returns_loading_text():
    """get_loading_data getter returns dict with 'loading_text' key."""
    from telegram_bot.dialogs.crm_ai_advisor import get_loading_data

    result = await get_loading_data()

    assert "loading_text" in result
    assert isinstance(result["loading_text"], str)
    assert len(result["loading_text"]) > 0


# --- on_advisor_action handler ---


async def test_on_advisor_action_sets_dialog_data_with_action():
    """on_advisor_action stores action in dialog_manager.dialog_data."""
    from telegram_bot.dialogs.crm_ai_advisor import on_advisor_action

    callback = MagicMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}
    manager.switch_to = AsyncMock()
    manager.middleware_data = {}
    manager.bg = MagicMock(return_value=MagicMock())

    await on_advisor_action(callback, widget, manager, "daily_plan")

    assert manager.dialog_data["advisor_action"] == "daily_plan"


async def test_on_advisor_action_switches_to_loading_not_result():
    """on_advisor_action switches to loading state, NOT to result directly."""
    from telegram_bot.dialogs.crm_ai_advisor import on_advisor_action
    from telegram_bot.dialogs.states import AIAdvisorSG

    callback = MagicMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}
    manager.switch_to = AsyncMock()
    manager.middleware_data = {}
    manager.bg = MagicMock(return_value=MagicMock())

    await on_advisor_action(callback, widget, manager, "deal_tips")

    manager.switch_to.assert_called_once_with(AIAdvisorSG.loading)


# --- get_advisor_result getter ---


async def test_get_advisor_result_reads_result_text_from_dialog_data():
    """get_advisor_result reads result_text from dialog_data (not calling service directly)."""
    from telegram_bot.dialogs.crm_ai_advisor import get_advisor_result

    advisor = MagicMock()
    advisor.get_daily_plan = AsyncMock()
    advisor.get_deal_and_task_tips = AsyncMock()

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {"result_text": "Заранее подготовленный ответ"}
    dialog_manager.middleware_data = {"ai_advisor_service": advisor}

    result = await get_advisor_result(dialog_manager=dialog_manager)

    # Should read from dialog_data, not call the service
    advisor.get_daily_plan.assert_not_called()
    advisor.get_deal_and_task_tips.assert_not_called()
    assert result["result_text"] == "Заранее подготовленный ответ"


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
