"""Tests for handoff qualification dialog (aiogram-dialog migration)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.handoff import (
    _GOAL_OPTIONS,
    _on_contact_chat,
    handoff_dialog,
)
from telegram_bot.dialogs.states import HandoffSG
from telegram_bot.handlers.handoff import (
    HandoffStates,
    parse_qual_callback,
    start_qualification,
)


def test_parse_qual_callback_goal():
    step, value = parse_qual_callback("qual:goal:search")
    assert step == "goal"
    assert value == "search"


def test_parse_qual_callback_services():
    step, value = parse_qual_callback("qual:goal:services")
    assert step == "goal"
    assert value == "services"


def test_parse_qual_callback_invalid():
    result = parse_qual_callback("other:data")
    assert result is None


def test_handoff_sg_states():
    """HandoffSG must have goal and contact states."""
    assert hasattr(HandoffSG, "goal")
    assert hasattr(HandoffSG, "contact")


def test_handoff_states_active():
    """HandoffStates.active FSM state must exist for handoff guard."""
    assert hasattr(HandoffStates, "active")


def test_goal_options_no_buy_rent():
    """buy/rent must not exist in goal options."""
    ids = [item[1] for item in _GOAL_OPTIONS]
    assert "buy" not in ids
    assert "rent" not in ids


def test_goal_options_values():
    """Goal options must contain search, services, consult, other."""
    ids = [item[1] for item in _GOAL_OPTIONS]
    assert ids == ["search", "services", "consult", "other"]


def test_goal_options_2_column_layout():
    """4 goal options should fit in 2x2 grid (width=2)."""
    assert len(_GOAL_OPTIONS) == 4


def test_handoff_dialog_has_two_windows():
    """Dialog must have exactly 2 windows (goal + contact)."""
    assert len(handoff_dialog.windows) == 2


def test_no_build_budget_keyboard():
    """build_budget_keyboard must not exist as module attribute."""
    from telegram_bot.handlers import handoff

    assert not hasattr(handoff, "build_budget_keyboard")


def test_no_build_goal_keyboard():
    """build_goal_keyboard removed — replaced by dialog."""
    from telegram_bot.handlers import handoff

    assert not hasattr(handoff, "build_goal_keyboard")


def test_no_build_contact_keyboard():
    """build_contact_keyboard removed — replaced by dialog."""
    from telegram_bot.handlers import handoff

    assert not hasattr(handoff, "build_contact_keyboard")


def test_no_qual_cache():
    """_qual_cache removed — dialog uses dialog_data."""
    from telegram_bot.handlers import handoff

    assert not hasattr(handoff, "_qual_cache")


def test_no_create_handoff_router():
    """create_handoff_router removed — replaced by handoff_dialog."""
    from telegram_bot.handlers import handoff

    assert not hasattr(handoff, "create_handoff_router")


def test_start_qualification_accepts_dialog_manager():
    """start_qualification must accept dialog_manager kwarg."""
    import inspect

    sig = inspect.signature(start_qualification)
    assert "dialog_manager" in sig.parameters


@pytest.mark.asyncio
async def test_on_contact_chat_uses_middleware_locale_for_handoff_completion():
    property_bot = MagicMock()
    property_bot._complete_handoff = AsyncMock()

    callback = MagicMock()
    callback.from_user = SimpleNamespace(id=7, full_name="Test User", username="tester")
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()

    manager = MagicMock()
    manager.start_data = {}
    manager.dialog_data = {"goal": "consult"}
    manager.middleware_data = {
        "property_bot": property_bot,
        "state": AsyncMock(),
        "locale": "en",
    }
    manager.done = AsyncMock()
    manager.show_mode = None

    await _on_contact_chat(callback, MagicMock(), manager)

    kwargs = property_bot._complete_handoff.await_args.kwargs
    assert kwargs["locale"] == "en"
