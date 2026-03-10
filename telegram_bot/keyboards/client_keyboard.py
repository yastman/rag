# telegram_bot/keyboards/client_keyboard.py
"""Client persistent ReplyKeyboard (#628)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


logger = logging.getLogger(__name__)


# Fallback button text -> action ID mapping (used when i18n not available)
MENU_BUTTONS: dict[str, str] = {
    "🏠 Подобрать квартиру": "search",
    "🔑 Услуги": "services",
    "📅 Запись на осмотр": "viewing",
    "👤 Связаться с менеджером": "manager",
    "💬 Задать вопрос": "ask",
    "📌 Мои закладки": "bookmarks",
    "🎯 Демонстрация": "demo",
}

# Reverse lookup: action_id -> button text (ru fallback)
ACTIONS_TO_TEXT: dict[str, str] = {v: k for k, v in MENU_BUTTONS.items()}

# FTL key -> action ID mapping
_ACTION_IDS: dict[str, str] = {
    "kb-search": "search",
    "kb-services": "services",
    "kb-viewing": "viewing",
    "kb-manager": "manager",
    "kb-ask": "ask",
    "kb-bookmarks": "bookmarks",
    "kb-demo": "demo",
}


def get_menu_button_texts(i18n_hub: Any = None) -> set[str]:
    """Return all supported menu labels for handler filters."""
    texts = set(MENU_BUTTONS.keys())
    # CATALOG_BUTTONS handled by catalog_router (StateFilter-based), not here
    if i18n_hub is None:
        return texts

    for locale in ("ru", "uk", "en"):
        try:
            translator = i18n_hub.get_translator_by_locale(locale)
            for ftl_key in _ACTION_IDS:
                label = translator.get(ftl_key)
                if isinstance(label, str) and label:
                    texts.add(label)
        except Exception:
            continue
    return texts


def build_client_keyboard(i18n: Any = None) -> ReplyKeyboardMarkup:
    """Build persistent 3x2 ReplyKeyboard for client.

    Args:
        i18n: FluentTranslator instance. When provided, button texts are
            resolved from .ftl keys. Falls back to hardcoded Russian text.
    """
    if i18n is not None:
        texts = [i18n.get(key) for key in _ACTION_IDS]
    else:
        texts = list(MENU_BUTTONS.keys())  # fallback to hardcoded Russian

    # Ensure exactly 7 buttons (pad or trim if needed)
    while len(texts) < 7:
        texts.append("")
    texts = texts[:7]

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts[0]), KeyboardButton(text=texts[1])],
            [KeyboardButton(text=texts[2]), KeyboardButton(text=texts[3])],
            [KeyboardButton(text=texts[4]), KeyboardButton(text=texts[5])],
            [KeyboardButton(text=texts[6])],  # Демонстрация — отдельный ряд
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# --- Catalog mode keyboard ---

CATALOG_BUTTONS: dict[str, str] = {
    "📥 Показать ещё 10": "catalog_more",
    "🔍 Фильтры": "catalog_filters",
    "📌 Избранное": "catalog_bookmarks",
    "🏠 Главное меню": "catalog_exit",
}


def build_catalog_keyboard(*, shown: int, total: int) -> ReplyKeyboardMarkup:
    """Build ReplyKeyboard for catalog browsing mode."""
    has_more = shown < total
    rows: list[list[KeyboardButton]] = []
    if has_more:
        rows.append(
            [
                KeyboardButton(text=f"📥 Показать ещё ({shown} из {total})"),
            ]
        )
    rows.append([KeyboardButton(text="🔍 Фильтры"), KeyboardButton(text="📌 Избранное")])
    rows.append(
        [
            KeyboardButton(text="📅 Запись на осмотр"),
            KeyboardButton(text="👤 Написать менеджеру"),
        ]
    )
    rows.append([KeyboardButton(text="🏠 Главное меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def parse_catalog_button(text: str) -> str | None:
    """Parse catalog keyboard button text to action ID."""
    if text.startswith("📥 Показать"):
        return "catalog_more"
    return CATALOG_BUTTONS.get(text)


def parse_menu_button(text: str, i18n_hub: Any = None) -> str | None:
    """Parse button text to action ID, checking all supported locales.

    Args:
        text: Button text from the user message.
        i18n_hub: TranslatorHub instance. When provided, looks up translations
            in all locales via hub.get_translator_by_locale().

    Returns:
        Action ID string or None if text doesn't match any known button.
    """
    if i18n_hub is not None:
        for locale in ("ru", "uk", "en"):
            try:
                t = i18n_hub.get_translator_by_locale(locale)
                for ftl_key, action_id in _ACTION_IDS.items():
                    if t.get(ftl_key) == text:
                        return action_id
            except Exception:
                logger.warning("Failed to parse menu button via i18n locale=%s", locale)

    # Fallback: check hardcoded MENU_BUTTONS (text -> action)
    return MENU_BUTTONS.get(text)
