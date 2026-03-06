"""Tests for demo button in client keyboard."""

from telegram_bot.keyboards.client_keyboard import (
    MENU_BUTTONS,
    build_client_keyboard,
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
