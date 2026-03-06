# telegram_bot/keyboards/property_card.py
"""Property card formatting and buttons (#628)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.callback_data import FavoriteCB, ResultsCB


if TYPE_CHECKING:
    from aiogram.types import Message

logger = logging.getLogger(__name__)


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


async def send_property_card(
    message: Message,
    result: dict[str, Any],
    *,
    favorites_service: Any = None,
    telegram_id: int | None = None,
) -> Message:
    """Send a property card with optional photo album and action buttons.

    Standalone version of PropertyBot._send_property_card (#907 DRY).
    Can be called from dialogs and handlers without a bot class instance.
    """
    from aiogram.types import FSInputFile, InputMediaPhoto

    p = result.get("payload", {})
    card = format_property_card(
        property_id=result.get("id", ""),
        complex_name=p.get("complex_name", ""),
        location=p.get("city", ""),
        property_type=p.get("property_type", ""),
        floor=p.get("floor", 0),
        area_m2=p.get("area_m2", 0),
        view=", ".join(p.get("view_tags", [])) or p.get("view_primary", ""),
        price_eur=p.get("price_eur", 0),
        section=p.get("section", ""),
        apartment_number=p.get("apartment_number", ""),
    )
    is_fav = False
    if favorites_service is not None and telegram_id is not None:
        is_fav = await favorites_service.is_favorited(telegram_id, result.get("id", ""))

    demo_photos = get_demo_photo_paths()
    reply_markup = build_card_buttons(result.get("id", ""), is_favorited=is_fav)

    photo_message_ids: list[int] = []
    if demo_photos:
        try:
            media = [InputMediaPhoto(media=FSInputFile(path)) for path in demo_photos]
            sent_photos = await message.answer_media_group(media=media)  # type: ignore[arg-type]
            photo_message_ids = [m.message_id for m in sent_photos]
        except Exception:
            logger.warning("Failed to send photo album, falling back to text card", exc_info=True)

    card_msg = await message.answer(card, reply_markup=reply_markup)
    card_msg._photo_message_ids = photo_message_ids  # type: ignore[attr-defined]
    return card_msg


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
