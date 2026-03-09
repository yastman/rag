"""Tests for handoff qualification inline-button flow."""

from telegram_bot.handlers.handoff import (
    build_contact_keyboard,
    build_goal_keyboard,
    parse_qual_callback,
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


def test_build_goal_keyboard_layout():
    """Row 1: search + services, Row 2: consult."""
    kb = build_goal_keyboard(i18n=None)
    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[0]) == 2
    assert len(kb.inline_keyboard[1]) == 1


def test_build_goal_keyboard_callbacks():
    kb = build_goal_keyboard(i18n=None)
    assert kb.inline_keyboard[0][0].callback_data == "qual:goal:search"
    assert kb.inline_keyboard[0][1].callback_data == "qual:goal:services"
    assert kb.inline_keyboard[1][0].callback_data == "qual:goal:consult"


def test_build_goal_keyboard_no_buy_rent():
    """buy/rent callbacks must not exist in the keyboard."""
    kb = build_goal_keyboard(i18n=None)
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "qual:goal:buy" not in all_callbacks
    assert "qual:goal:rent" not in all_callbacks


def test_no_build_budget_keyboard():
    """build_budget_keyboard must not exist as module attribute."""
    from telegram_bot.handlers import handoff

    assert not hasattr(handoff, "build_budget_keyboard")


def test_build_contact_keyboard():
    kb = build_contact_keyboard(i18n=None)
    assert len(kb.inline_keyboard) == 1  # 1 row: 2 buttons
    assert kb.inline_keyboard[0][0].callback_data == "qual:contact:chat"
    assert kb.inline_keyboard[0][1].callback_data == "qual:contact:phone"
