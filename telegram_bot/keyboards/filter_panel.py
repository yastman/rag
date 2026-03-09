"""Inline filter panel for apartment catalog — edit-in-place single message."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.callback_data import FilterPanelCB


# Display maps for human-readable filter values
_ROOMS_DISPLAY: dict[int, str] = {
    0: "Студия",
    1: "Студия",
    2: "1-спальня",
    3: "2-спальни",
    4: "3-спальни",
    5: "4+ спальни",
}


_CITY_OPTIONS: list[str] = [
    "Солнечный берег",
    "Свети Влас",
    "Несебр",
    "Поморие",
    "Бургас",
    "Варна",
    "Созополь",
]

_ROOMS_OPTIONS: list[tuple[str, int]] = [
    ("Студия", 1),
    ("1-спальня", 2),
    ("2-спальни", 3),
    ("3-спальни", 4),
    ("4+ спальни", 5),
]

_BUDGET_OPTIONS: list[tuple[str, str]] = [
    ("До 50 000 €", "low"),
    ("50 000 – 100 000 €", "mid"),
    ("100 000 – 150 000 €", "high"),
    ("150 000 – 200 000 €", "premium"),
    ("Более 200 000 €", "luxury"),
]


def build_filter_panel_text(*, filters: dict, count: int) -> str:
    """Build filter panel message text with active filters and count."""
    lines = ["🏠 Поиск апартаментов\n"]
    if filters.get("city"):
        lines.append(f"📍 Город: {filters['city']}")
    if filters.get("rooms") is not None:
        rooms = filters["rooms"]
        display = _ROOMS_DISPLAY.get(int(rooms), f"{rooms} комн.")
        lines.append(f"🛏 Комнаты: {display}")
    if filters.get("price_eur"):
        p = filters["price_eur"]
        if isinstance(p, dict):
            parts = []
            if p.get("gte"):
                parts.append(f"от {p['gte']:,.0f} €")
            if p.get("lte"):
                parts.append(f"до {p['lte']:,.0f} €")
            lines.append(f"💰 Бюджет: {' '.join(parts)}")
    if filters.get("view_tags"):
        lines.append(f"🌅 Вид: {', '.join(filters['view_tags'])}")
    if filters.get("floor"):
        lines.append(f"🏢 Этаж: {filters['floor']}")
    if filters.get("area_m2"):
        lines.append(f"📐 Площадь: {filters['area_m2']}")
    if filters.get("complex_name"):
        lines.append(f"🏘 Комплекс: {filters['complex_name']}")
    if filters.get("is_furnished") is not None:
        lines.append(f"🛋 Мебель: {'Да' if filters['is_furnished'] else 'Нет'}")
    if filters.get("is_promotion"):
        lines.append("🏷 Акции: Да")
    lines.append(f"\nНайдено: {count} апартаментов")
    return "\n".join(lines)


def build_filter_panel_keyboard(*, count: int = 0) -> InlineKeyboardMarkup:
    """Build inline keyboard for filter panel main screen."""

    def _fb(label: str, field: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=label,
            callback_data=FilterPanelCB(action="select", field=field).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_fb("🏙 Город ▼", "city"), _fb("🛏 Комнаты ▼", "rooms"), _fb("💰 Бюджет ▼", "budget")],
            [_fb("🌅 Вид ▼", "view"), _fb("📐 Площадь ▼", "area"), _fb("🏢 Этаж ▼", "floor")],
            [
                _fb("🏘 Комплекс ▼", "complex"),
                _fb("🛋 Мебель ▼", "furnished"),
                _fb("🏷 Акции ▼", "promotion"),
            ],
            [
                InlineKeyboardButton(
                    text=f"🔍 Применить ({count})",
                    callback_data=FilterPanelCB(action="apply", field="").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Сбросить фильтры",
                    callback_data=FilterPanelCB(action="reset", field="").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Назад к результатам",
                    callback_data=FilterPanelCB(action="back", field="").pack(),
                )
            ],
        ]
    )


def build_filter_options_keyboard(
    field: str,
    *,
    current_value: str | int | None = None,
) -> InlineKeyboardMarkup:
    """Build sub-menu keyboard for selecting a filter value."""
    rows: list[list[InlineKeyboardButton]] = []

    if field == "city":
        any_btn = InlineKeyboardButton(
            text="✅ Любой город" if current_value is None else "Любой город",
            callback_data=FilterPanelCB(action="set", field="city", value="").pack(),
        )
        rows.append([any_btn])
        for city in _CITY_OPTIONS:
            label = f"✅ {city}" if city == current_value else city
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=FilterPanelCB(action="set", field="city", value=city).pack(),
                    )
                ]
            )

    elif field == "rooms":
        any_btn = InlineKeyboardButton(
            text="✅ Любое кол-во" if current_value is None else "Любое кол-во",
            callback_data=FilterPanelCB(action="set", field="rooms", value="").pack(),
        )
        rows.append([any_btn])
        for label, value in _ROOMS_OPTIONS:
            is_current = int(current_value) == value if current_value is not None else False
            display = f"✅ {label}" if is_current else label
            rows.append(
                [
                    InlineKeyboardButton(
                        text=display,
                        callback_data=FilterPanelCB(
                            action="set", field="rooms", value=str(value)
                        ).pack(),
                    )
                ]
            )

    elif field == "budget":
        any_btn = InlineKeyboardButton(
            text="✅ Любой бюджет" if current_value is None else "Любой бюджет",
            callback_data=FilterPanelCB(action="set", field="budget", value="").pack(),
        )
        rows.append([any_btn])
        for label, value in _BUDGET_OPTIONS:
            is_current = current_value == value
            display = f"✅ {label}" if is_current else label
            rows.append(
                [
                    InlineKeyboardButton(
                        text=display,
                        callback_data=FilterPanelCB(
                            action="set", field="budget", value=value
                        ).pack(),
                    )
                ]
            )

    elif field == "furnished":
        is_yes = current_value is True or current_value == "true"
        is_no = current_value is False or current_value == "false"
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Да" if is_yes else "Да",
                    callback_data=FilterPanelCB(
                        action="set", field="furnished", value="true"
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Нет" if is_no else "Нет",
                    callback_data=FilterPanelCB(
                        action="set", field="furnished", value="false"
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Любое" if current_value is None else "Любое",
                    callback_data=FilterPanelCB(action="set", field="furnished", value="").pack(),
                )
            ]
        )

    elif field == "promotion":
        is_yes = current_value is True or current_value == "true"
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Да" if is_yes else "Да",
                    callback_data=FilterPanelCB(
                        action="set", field="promotion", value="true"
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Нет" if not is_yes else "Нет",
                    callback_data=FilterPanelCB(
                        action="set", field="promotion", value="false"
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Любое" if current_value is None else "Любое",
                    callback_data=FilterPanelCB(action="set", field="promotion", value="").pack(),
                )
            ]
        )

    else:
        # Generic text-based filter (view, area, floor, complex) — placeholder
        rows.append(
            [
                InlineKeyboardButton(
                    text="Любое",
                    callback_data=FilterPanelCB(action="set", field=field, value="").pack(),
                )
            ]
        )

    # Back button always last
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад к фильтрам",
                callback_data=FilterPanelCB(action="main", field="").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)
