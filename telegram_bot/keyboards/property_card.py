# telegram_bot/keyboards/property_card.py
"""Property card formatting and buttons (#628)."""

from __future__ import annotations

from pathlib import Path

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.callback_data import FavoriteCB, ResultsCB


_DEMO_PHOTO_DIR = Path(__file__).resolve().parents[1] / "static" / "photos" / "demo"
_DEMO_PHOTOS: list[Path] = sorted(_DEMO_PHOTO_DIR.glob("*.jpg")) if _DEMO_PHOTO_DIR.exists() else []


def get_demo_photo_paths() -> list[Path]:
    """Return existing demo photo paths (jpg)."""
    return [p for p in _DEMO_PHOTOS if p.exists()]


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
    section: str = "",
    apartment_number: str = "",
) -> str:
    """Format property as text card."""
    price_formatted = f"{int(price_eur):,}".replace(",", " ")
    lines = [f"🏠 Комплекс: {complex_name}"]
    if section:
        lines.append(f"🏗 Секция: {section}")
    if apartment_number:
        lines.append(f"🚪 №: {apartment_number}")
    if location:
        lines.append(f"📍 Город: {location}")
    if property_type:
        lines.append(f"🛏 Тип: {property_type}")
    if floor:
        lines.append(f"🔼 Этаж: {floor}")
    if area_m2:
        lines.append(f"📐 Площадь: {area_m2} м²")
    if view:
        lines.append(f"🌅 Вид: {view}")
    lines.append(f"💰 Цена: {price_formatted} €")
    return "\n".join(lines)


def format_promotion_card(
    *,
    property_id: str,
    complex_name: str,
    rooms: int,
    floor: int,
    area_m2: int | float,
    view: str,
    price_eur: int | float,
    old_price_eur: int | float,
) -> str:
    """Format apartment with active promotion, showing old/new price and discount %."""
    discount_pct = round((1 - price_eur / old_price_eur) * 100) if old_price_eur else 0
    price_new = f"{int(price_eur):,}".replace(",", " ")
    price_old = f"{int(old_price_eur):,}".replace(",", " ")
    rooms_text = {1: "Студия", 2: "1-спальня", 3: "2-спальни", 4: "3-спальни"}.get(
        rooms, str(rooms)
    )
    return (
        f"🔥 {complex_name}\n"
        f"{rooms_text} · {floor} этаж · {area_m2} м² · {view}\n"
        f"💰 {price_old} € → {price_new} € (-{discount_pct}%)"
    )


def build_card_buttons(
    property_id: str,
    *,
    is_favorited: bool = False,
) -> InlineKeyboardMarkup:
    """Build inline buttons for a property card (2+1 layout)."""
    if is_favorited:
        fav_btn = InlineKeyboardButton(
            text="❌ Убрать из избранного",
            callback_data=FavoriteCB(action="remove", apartment_id=property_id).pack(),
        )
    else:
        fav_btn = InlineKeyboardButton(
            text="📌 В избранное",
            callback_data=FavoriteCB(action="add", apartment_id=property_id).pack(),
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 На осмотр",
                    callback_data=f"card:viewing:{property_id}",
                ),
                fav_btn,
            ],
            [
                InlineKeyboardButton(
                    text="💬 Уточнить у менеджера",
                    callback_data=f"card:ask:{property_id}",
                ),
            ],
        ]
    )


def build_results_footer(*, shown_total: int, total: int, has_more: bool) -> InlineKeyboardMarkup:
    """Build footer buttons after property results."""
    rows = []
    if has_more:
        remaining = max(total - shown_total, 0)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔄 Показать ещё ({remaining} осталось)",
                    callback_data=ResultsCB(action="more").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⚙️ Изменить параметры",
                callback_data=ResultsCB(action="refine").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="📅 Запись на осмотр",
                callback_data=ResultsCB(action="viewing").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
