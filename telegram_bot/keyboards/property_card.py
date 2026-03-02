# telegram_bot/keyboards/property_card.py
"""Property card formatting and buttons (#628)."""

from __future__ import annotations

from pathlib import Path

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


_DEMO_PHOTOS_DIR = Path(__file__).resolve().parent.parent / "static" / "photos" / "demo"
_DEMO_PHOTOS: list[Path] = (
    sorted(_DEMO_PHOTOS_DIR.glob("*.jpg")) if _DEMO_PHOTOS_DIR.exists() else []
)


def get_demo_photos() -> list[Path]:
    """Return list of demo photo paths (for all apartments until real photos exist)."""
    return _DEMO_PHOTOS


def get_main_demo_photo() -> Path | None:
    """Return first demo photo as main card image."""
    return _DEMO_PHOTOS[0] if _DEMO_PHOTOS else None


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
    photo_count: int = 0,
) -> InlineKeyboardMarkup:
    """Build inline buttons for a property card (photo + 2+1 layout)."""
    if is_favorited:
        fav_btn = InlineKeyboardButton(
            text="❌ Убрать из избранного",
            callback_data=f"fav:remove:{property_id}",
        )
    else:
        fav_btn = InlineKeyboardButton(
            text="📌 В избранное",
            callback_data=f"fav:add:{property_id}",
        )
    rows: list[list[InlineKeyboardButton]] = []
    if photo_count > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📷 Все фото ({photo_count})",
                    callback_data=f"card:photos:{property_id}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="📅 На осмотр",
                callback_data=f"card:viewing:{property_id}",
            ),
            fav_btn,
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="💬 Уточнить у менеджера",
                callback_data=f"card:ask:{property_id}",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_results_footer(*, shown: int, total: int, has_more: bool) -> InlineKeyboardMarkup:
    """Build footer buttons after property results."""
    rows = []
    if has_more:
        rows.append([InlineKeyboardButton(text="🔄 Показать ещё", callback_data="results:more")])
    rows.append([InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data="results:refine")])
    rows.append([InlineKeyboardButton(text="📅 Запись на осмотр", callback_data="results:viewing")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
