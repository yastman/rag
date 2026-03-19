"""Tests for the dedicated catalog reply keyboard."""

from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard, parse_catalog_button


def test_build_catalog_keyboard_shows_more_button_when_more_results_exist() -> None:
    kb = build_catalog_keyboard(shown=10, total=47)
    first_row = [button.text for button in kb.keyboard[0]]
    assert first_row == ["📥 Показать ещё (10 из 47)"]


def test_parse_catalog_button_maps_static_actions() -> None:
    assert parse_catalog_button("🔍 Фильтры") == "catalog_filters"
    assert parse_catalog_button("🏠 Главное меню") == "catalog_exit"
