"""Inline filter panel for apartment catalog — edit-in-place single message."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.callback_data import FilterPanelCB


# Human-readable display maps
_ROOMS_DISPLAY: dict[int, str] = {
    0: "Студия",
    1: "Студия",
    2: "1-спальня",
    3: "2-спальни",
    4: "3-спальни",
    5: "4+ спальни",
}

_BUDGET_OPTIONS: list[tuple[str, str]] = [
    ("low", "До 50 000 €"),
    ("mid", "50 000 – 100 000 €"),
    ("high", "100 000 – 150 000 €"),
    ("premium", "150 000 – 200 000 €"),
    ("luxury", "Более 200 000 €"),
]

_CITY_OPTIONS: list[str] = [
    "Солнечный берег",
    "Свети Влас",
    "Несебр",
    "Бургас",
    "Варна",
    "Созополь",
]

_VIEW_OPTIONS: list[str] = ["Море", "Горы", "Бассейн", "Парк", "Город"]

_AREA_OPTIONS: list[tuple[str, str]] = [
    ("small", "До 40 м²"),
    ("medium", "40 – 80 м²"),
    ("large", "80 – 120 м²"),
    ("xlarge", "Более 120 м²"),
]

_FLOOR_OPTIONS: list[tuple[str, str]] = [
    ("low", "1–3 этаж"),
    ("mid", "4–7 этаж"),
    ("high", "8+ этаж"),
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
                parts.append(f"от {p['gte']:,.0f} €".replace(",", " "))
            if p.get("lte"):
                parts.append(f"до {p['lte']:,.0f} €".replace(",", " "))
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
    current_value: str | int | None = None,
) -> InlineKeyboardMarkup:
    """Build inline keyboard for a specific filter sub-menu.

    Shows available options with checkmark on currently selected value.
    Always includes a back button as the last row.
    """
    rows: list[list[InlineKeyboardButton]] = []

    if field == "city":
        rows.extend(_build_city_options(current_value))
    elif field == "rooms":
        rows.extend(_build_rooms_options(current_value))
    elif field == "budget":
        rows.extend(_build_budget_options(current_value))
    elif field == "view":
        rows.extend(_build_view_options(current_value))
    elif field == "area":
        rows.extend(_build_area_options(current_value))
    elif field == "floor":
        rows.extend(_build_floor_options(current_value))
    elif field == "furnished" or field == "promotion":
        rows.extend(_build_bool_options(field, current_value, "Да", "Нет"))
    elif field == "complex":
        rows.extend(_build_complex_options(current_value))
    else:
        rows.append([_any_btn(field)])

    # Back button
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=FilterPanelCB(action="back", field=field).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Option builders ---


def _check(label: str, is_active: bool) -> str:
    return f"✅ {label}" if is_active else label


def _set_btn(field: str, value: str, label: str, is_active: bool = False) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=_check(label, is_active),
        callback_data=FilterPanelCB(action="set", field=field, value=value).pack(),
    )


def _any_btn(field: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="Любой",
        callback_data=FilterPanelCB(action="set", field=field, value="").pack(),
    )


def _build_city_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for city in _CITY_OPTIONS:
        rows.append([_set_btn("city", city, city, city == current)])
    rows.append([_any_btn("city")])
    return rows


def _build_rooms_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    options = [
        (1, "Студия"),
        (2, "1-спальня"),
        (3, "2-спальни"),
        (4, "3-спальни"),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for val, label in options:
        is_active = current is not None and int(current) == val
        rows.append([_set_btn("rooms", str(val), label, is_active)])
    rows.append([_any_btn("rooms")])
    return rows


def _build_budget_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in _BUDGET_OPTIONS:
        rows.append([_set_btn("budget", key, label, key == current)])
    rows.append([_any_btn("budget")])
    return rows


def _build_view_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for view in _VIEW_OPTIONS:
        view_lower = view.lower()
        is_active = isinstance(current, (list, str)) and (
            view_lower in current
            if isinstance(current, list)
            else view_lower == str(current).lower()
        )
        rows.append([_set_btn("view", view_lower, view, is_active)])
    rows.append([_any_btn("view")])
    return rows


def _build_area_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in _AREA_OPTIONS:
        rows.append([_set_btn("area", key, label, key == current)])
    rows.append([_any_btn("area")])
    return rows


def _build_floor_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in _FLOOR_OPTIONS:
        rows.append([_set_btn("floor", key, label, key == current)])
    rows.append([_any_btn("floor")])
    return rows


def _build_bool_options(
    field: str,
    current: str | int | None,
    yes_label: str,
    no_label: str,
) -> list[list[InlineKeyboardButton]]:
    yes_active = current is True or current == "true" or current == "yes"
    no_active = current is False or current == "false" or current == "no"
    return [
        [_set_btn(field, "true", yes_label, yes_active)],
        [_set_btn(field, "false", no_label, no_active)],
        [_any_btn(field)],
    ]


def _build_complex_options(current: str | int | None) -> list[list[InlineKeyboardButton]]:
    # Комплексы могут быть динамическими, пока заглушка
    return [[_any_btn("complex")]]
