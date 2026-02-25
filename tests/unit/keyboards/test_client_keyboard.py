# tests/unit/keyboards/test_client_keyboard.py
"""Tests for client ReplyKeyboard."""

from telegram_bot.keyboards.client_keyboard import (
    MENU_BUTTONS,
    build_client_keyboard,
    parse_menu_button,
)


# --- Locale-aware tests ---


def test_build_default_ru():
    from aiogram.types import ReplyKeyboardMarkup

    kb = build_client_keyboard(locale="ru")
    assert isinstance(kb, ReplyKeyboardMarkup)
    buttons = [btn.text for row in kb.keyboard for btn in row]
    assert len(buttons) == 6
    assert any("апарт" in b.lower() or "apartments" in b.lower() or "апарт" in b for b in buttons)


def test_build_uk():
    from aiogram.types import ReplyKeyboardMarkup

    kb = build_client_keyboard(locale="uk")
    assert isinstance(kb, ReplyKeyboardMarkup)
    buttons = [btn.text for row in kb.keyboard for btn in row]
    assert len(buttons) == 6
    assert any("апартамент" in b.lower() for b in buttons)


def test_parse_ru_button():
    assert parse_menu_button("🏠 Подбор апартаментов") == "search"
    assert parse_menu_button("🔑 Услуги") == "services"


def test_parse_uk_button():
    assert parse_menu_button("🏠 Підбір апартаментів") == "search"
    assert parse_menu_button("🔑 Послуги") == "services"


def test_parse_en_button():
    assert parse_menu_button("🏠 Find Apartments") == "search"
    assert parse_menu_button("🔑 Services") == "services"


def test_parse_unknown_returns_none():
    assert parse_menu_button("totally unknown text xyz") is None


def test_build_client_keyboard_returns_markup():
    from aiogram.types import ReplyKeyboardMarkup

    kb = build_client_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup)


def test_keyboard_has_3_rows():
    kb = build_client_keyboard()
    assert len(kb.keyboard) == 3


def test_keyboard_has_6_buttons():
    kb = build_client_keyboard()
    buttons = [btn for row in kb.keyboard for btn in row]
    assert len(buttons) == 6


def test_keyboard_is_persistent():
    kb = build_client_keyboard()
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True


def test_menu_buttons_has_6_entries():
    assert len(MENU_BUTTONS) == 6


def test_parse_menu_button_known():
    assert parse_menu_button("🏠 Подбор апартаментов") == "search"
    assert parse_menu_button("🔑 Услуги") == "services"
    assert parse_menu_button("📅 Запись на осмотр") == "viewing"
    assert parse_menu_button("📌 Мои закладки") == "bookmarks"
    assert parse_menu_button("🎁 Акции") == "promotions"
    assert parse_menu_button("👤 Связь с менеджером") == "manager"


def test_parse_menu_button_unknown():
    assert parse_menu_button("random text") is None
