"""Dedicated reply keyboard helpers for the catalog flow."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


CATALOG_BUTTONS = {
    "🔍 Фильтры": "catalog_filters",
    "📌 Избранное": "catalog_bookmarks",
    "📅 Запись на осмотр": "catalog_viewing",
    "👤 Написать менеджеру": "catalog_manager",
    "🏠 Главное меню": "catalog_exit",
}


def build_catalog_keyboard(*, shown: int, total: int) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if shown < total:
        rows.append([KeyboardButton(text=f"📥 Показать ещё ({shown} из {total})")])
    rows.append([KeyboardButton(text="🔍 Фильтры"), KeyboardButton(text="📌 Избранное")])
    rows.append(
        [
            KeyboardButton(text="📅 Запись на осмотр"),
            KeyboardButton(text="👤 Написать менеджеру"),
        ]
    )
    rows.append([KeyboardButton(text="🏠 Главное меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def parse_catalog_button(text: str) -> str | None:
    if text.startswith("📥 Показать"):
        return "catalog_more"
    return CATALOG_BUTTONS.get(text)
