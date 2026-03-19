"""Catalog reply-keyboard contracts."""

from aiogram.types import ReplyKeyboardMarkup


def test_build_catalog_keyboard_returns_reply_markup() -> None:
    from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard

    kb = build_catalog_keyboard(shown=10, total=25)

    assert isinstance(kb, ReplyKeyboardMarkup)
    texts = [button.text for row in kb.keyboard for button in row]
    assert "🔄 Показать ещё" in texts
    assert "🔍 Фильтры" in texts
    assert "📌 Избранное" in texts
    assert "🏠 Главное меню" in texts


def test_build_catalog_keyboard_hides_show_more_on_last_page() -> None:
    from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard

    kb = build_catalog_keyboard(shown=25, total=25)

    texts = [button.text for row in kb.keyboard for button in row]
    assert "🔄 Показать ещё" not in texts


def test_parse_catalog_button_maps_known_actions() -> None:
    from telegram_bot.keyboards.catalog_keyboard import parse_catalog_button

    assert parse_catalog_button("🔄 Показать ещё") == "catalog_more"
    assert parse_catalog_button("🔍 Фильтры") == "catalog_filters"
    assert parse_catalog_button("📌 Избранное") == "catalog_bookmarks"
    assert parse_catalog_button("📅 Запись на осмотр") == "catalog_viewing"
    assert parse_catalog_button("👤 Написать менеджеру") == "catalog_manager"
    assert parse_catalog_button("🏠 Главное меню") == "catalog_home"
