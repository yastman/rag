# telegram_bot/keyboards/property_card.py
"""Property card formatting and buttons (#628)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def format_property_card(
    *,
    property_id: str,
    complex_name: str,
    location: str,
    property_type: str,
    floor: int,
    area_m2: int | float,
    view: str,
    price_eur: int | float,
) -> str:
    """Format property as text card."""
    price_formatted = f"{int(price_eur):,}".replace(",", " ")
    return (
        f"🏠 {complex_name}, {location}\n"
        f"{property_type} · {floor} этаж · {area_m2} м² · {view}\n"
        f"💰 {price_formatted} €"
    )


def build_card_buttons(property_id: str) -> InlineKeyboardMarkup:
    """Build inline buttons for a property card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 В закладки", callback_data=f"fav:add:{property_id}")],
        ]
    )


def build_results_footer(*, shown: int, total: int, has_more: bool) -> InlineKeyboardMarkup:
    """Build footer buttons after property results."""
    rows = []
    if has_more:
        rows.append([InlineKeyboardButton(text="🔄 Показать ещё", callback_data="results:more")])
    rows.append([InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data="results:refine")])
    rows.append([InlineKeyboardButton(text="📅 Запись на осмотр", callback_data="results:viewing")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
