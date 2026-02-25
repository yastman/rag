# telegram_bot/keyboards/client_keyboard.py
"""Client persistent ReplyKeyboard (#628)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from telegram_bot.services.content_loader import get_menu_buttons


# Fallback button text -> action ID mapping (used when YAML not yet loaded)
MENU_BUTTONS: dict[str, str] = {
    "🏠 Подбор апартаментов": "search",
    "🔑 Услуги": "services",
    "📅 Запись на осмотр": "viewing",
    "📌 Мои закладки": "bookmarks",
    "🎁 Акции": "promotions",
    "👤 Связь с менеджером": "manager",
}

# Reverse lookup: action_id -> button text (ru fallback)
ACTIONS_TO_TEXT: dict[str, str] = {v: k for k, v in MENU_BUTTONS.items()}


def build_client_keyboard(locale: str = "ru") -> ReplyKeyboardMarkup:
    """Build persistent 3x2 ReplyKeyboard for client in the given locale."""
    buttons_map = get_menu_buttons(locale)
    if not buttons_map:
        # Fallback to hardcoded Russian buttons
        buttons_map = {v: k for k, v in MENU_BUTTONS.items()}
    texts = list(buttons_map.values())
    # Ensure exactly 6 buttons (pad or trim if YAML is malformed)
    while len(texts) < 6:
        texts.append("")
    texts = texts[:6]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts[0]), KeyboardButton(text=texts[1])],
            [KeyboardButton(text=texts[2]), KeyboardButton(text=texts[3])],
            [KeyboardButton(text=texts[4]), KeyboardButton(text=texts[5])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def parse_menu_button(text: str) -> str | None:
    """Parse button text to action ID, checking all supported locales.

    Returns None if the text doesn't match any known menu button.
    Searches ru/uk/en so the user can send buttons in any language.
    """
    for locale in ("ru", "uk", "en"):
        buttons_map = get_menu_buttons(locale)  # {action_id: button_text}
        for action_id, btn_text in buttons_map.items():
            if btn_text == text:
                return action_id
    # Fallback: check hardcoded MENU_BUTTONS (text -> action)
    return MENU_BUTTONS.get(text)
