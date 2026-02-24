# telegram_bot/keyboards/client_keyboard.py
"""Client persistent ReplyKeyboard (#628)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


# Button text -> action ID mapping
MENU_BUTTONS: dict[str, str] = {
    "🏠 Подбор апартаментов": "search",
    "🔑 Услуги": "services",
    "📅 Запись на осмотр": "viewing",
    "📌 Мои закладки": "bookmarks",
    "🎁 Акции": "promotions",
    "👤 Связь с менеджером": "manager",
}

# Reverse lookup: action_id -> button text
ACTIONS_TO_TEXT: dict[str, str] = {v: k for k, v in MENU_BUTTONS.items()}


def build_client_keyboard() -> ReplyKeyboardMarkup:
    """Build persistent 3x2 ReplyKeyboard for client."""
    buttons = list(MENU_BUTTONS.keys())
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=buttons[0]), KeyboardButton(text=buttons[1])],
            [KeyboardButton(text=buttons[2]), KeyboardButton(text=buttons[3])],
            [KeyboardButton(text=buttons[4]), KeyboardButton(text=buttons[5])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def parse_menu_button(text: str) -> str | None:
    """Parse button text to action ID. Returns None if not a menu button."""
    return MENU_BUTTONS.get(text)
