# telegram_bot/keyboards/property_card.py
"""Property card formatting and buttons (#628)."""

from __future__ import annotations

from pathlib import Path

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


_DEMO_PHOTO_DIR = Path(__file__).resolve().parents[1] / "static" / "photos" / "demo"
_DEMO_PHOTO_FILES = ("demo_1.png", "demo_2.png", "demo_3.png")


def get_demo_photo_paths() -> list[str]:
    """Return existing demo photo paths used as temporary card images."""
    paths: list[str] = []
    for name in _DEMO_PHOTO_FILES:
        path = _DEMO_PHOTO_DIR / name
        if path.exists():
            paths.append(str(path))
    return paths


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
    photos_count: int | None = None,
) -> InlineKeyboardMarkup:
    """Build inline buttons for a property card (2+1+1 layout)."""
    total_photos = photos_count if photos_count is not None else len(get_demo_photo_paths()) or 3
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
            [
                InlineKeyboardButton(
                    text=f"📷 Все фото ({total_photos})",
                    callback_data=f"card:photos:{property_id}",
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
                    callback_data="results:more",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data="results:refine")])
    rows.append([InlineKeyboardButton(text="📅 Запись на осмотр", callback_data="results:viewing")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
