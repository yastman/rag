"""Tests for handoff qualification inline-button flow."""

from telegram_bot.handlers.handoff import (
    build_budget_keyboard,
    build_contact_keyboard,
    build_goal_keyboard,
    parse_qual_callback,
)


def test_parse_qual_callback_goal():
    step, value = parse_qual_callback("qual:goal:buy")
    assert step == "goal"
    assert value == "buy"


def test_parse_qual_callback_budget():
    step, value = parse_qual_callback("qual:budget:50-100")
    assert step == "budget"
    assert value == "50-100"


def test_parse_qual_callback_invalid():
    result = parse_qual_callback("other:data")
    assert result is None


def test_build_goal_keyboard():
    # Pass a mock i18n that returns the key as-is.
    kb = build_goal_keyboard(i18n=None)
    # Row 1: buy + rent, Row 2: consult.
    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[0]) == 2
    assert len(kb.inline_keyboard[1]) == 1
    assert kb.inline_keyboard[0][0].callback_data == "qual:goal:buy"
    assert kb.inline_keyboard[0][1].callback_data == "qual:goal:rent"
    assert kb.inline_keyboard[1][0].callback_data == "qual:goal:consult"


def test_build_budget_keyboard():
    kb = build_budget_keyboard(i18n=None)
    assert len(kb.inline_keyboard) == 2  # 2 rows: [3 buttons] + [1 button]
    assert kb.inline_keyboard[0][0].callback_data == "qual:budget:low"


def test_build_contact_keyboard():
    kb = build_contact_keyboard(i18n=None)
    assert len(kb.inline_keyboard) == 1  # 1 row: 2 buttons
    assert kb.inline_keyboard[0][0].callback_data == "qual:contact:chat"
    assert kb.inline_keyboard[0][1].callback_data == "qual:contact:phone"
