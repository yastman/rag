"""Tests for demo button in client keyboard and demo keyboard builders (#3411).

The demo journey is exercised in-process here and in
``tests/unit/dialogs/test_demo_dialog.py``; these are unit checks, not E2E.
"""

from telegram_bot.callback_data import DemoCB
from telegram_bot.keyboards.client_keyboard import (
    MENU_BUTTONS,
    build_client_keyboard,
)
from telegram_bot.keyboards.demo_keyboard import (
    DEFAULT_EXAMPLES,
    build_demo_examples,
    build_demo_menu,
)


def test_menu_buttons_has_demo():
    assert "🎯 Демонстрация" in MENU_BUTTONS
    assert MENU_BUTTONS["🎯 Демонстрация"] == "demo"


def test_keyboard_has_7_buttons():
    kb = build_client_keyboard()
    all_buttons = [btn.text for row in kb.keyboard for btn in row]
    assert len(all_buttons) == 7
    assert "🎯 Демонстрация" in all_buttons


def test_demo_is_last_row_alone():
    kb = build_client_keyboard()
    last_row = kb.keyboard[-1]
    assert len(last_row) == 1
    assert last_row[0].text == "🎯 Демонстрация"


# --- Demo keyboard builders (#3411, moved from the mislabeled demo E2E suite) ---


def test_demo_menu_has_apartments_button():
    kb = build_demo_menu()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "🏖 Подбор апартаментов" in texts


def test_demo_examples_keyboard():
    kb = build_demo_examples(DEFAULT_EXAMPLES)
    assert len(kb.inline_keyboard) == 4


def test_demo_menu_uses_callback_data():
    """Demo menu buttons use DemoCB callback_data, not raw strings."""
    kb = build_demo_menu()
    btn = kb.inline_keyboard[0][0]
    unpacked = DemoCB.unpack(btn.callback_data)
    assert unpacked.action == "apartments"


def test_demo_examples_use_callback_data():
    """Example buttons use DemoCB with idx."""
    kb = build_demo_examples(["Query A", "Query B"])
    for i, row in enumerate(kb.inline_keyboard):
        unpacked = DemoCB.unpack(row[0].callback_data)
        assert unpacked.action == "example"
        assert unpacked.idx == i
