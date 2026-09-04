"""Funnel dialog — constants, filter builder, and apartment list formatter."""

from __future__ import annotations

from typing import Any

from src.runtime.domain_defaults import DEMO_CITIES, DEMO_COMPLEX_CITIES
from telegram_bot.dialogs.filter_constants import (
    AREA_MAP as _AREA_MAP,
)
from telegram_bot.dialogs.filter_constants import (
    BUDGET_MAP as _BUDGET_MAP,
)
from telegram_bot.dialogs.filter_constants import (
    FLOOR_MAP as _FLOOR_MAP,
)
from telegram_bot.dialogs.filter_constants import (
    ROOMS_DISPLAY as _ROOMS_DISPLAY,
)
from telegram_bot.dialogs.filter_constants import (
    ROOMS_MAP as _ROOMS_MAP,
)
from telegram_bot.dialogs.filter_constants import (
    VIEW_DISPLAY as _VIEW_DISPLAY,
)


# City / complex / section selection options
# Fallback options are derived from the canonical demo domain (#3203) so the
# funnel never offers a city or complex that the demo seed does not contain.
_CITY_OPTIONS: list[tuple[str, str]] = [(city, city) for city in DEMO_CITIES] + [
    ("Любой город", "any"),
]

_COMPLEX_OPTIONS: list[tuple[str, str]] = [(name, name) for name in sorted(DEMO_COMPLEX_CITIES)] + [
    ("Любой комплекс", "any"),
]

_SECTION_OPTIONS: list[tuple[str, str]] = [
    ("A", "A"),
    ("A-2", "A-2"),
    ("A-A", "A-A"),
    ("A-B", "A-B"),
    ("B", "B"),
    ("B-1", "B-1"),
    ("B-2", "B-2"),
    ("B-3", "B-3"),
    ("B-5", "B-5"),
    ("B-6", "B-6"),
    ("B-V", "B-V"),
    ("C-2", "C-2"),
    ("C-5", "C-5"),
    ("D-1", "D-1"),
    ("D-2", "D-2"),
    ("D-3", "D-3"),
    ("E-1", "E-1"),
    ("E-2", "E-2"),
    ("E-3", "E-3"),
    ("E-4", "E-4"),
    ("F-1", "F-1"),
    ("F-2", "F-2"),
    ("F-3", "F-3"),
    ("F-4", "F-4"),
    ("V-D", "V-D"),
    ("V-G", "V- G"),
    ("Любая секция", "any"),
]

_PROPERTY_TYPE_DISPLAY: dict[str, str] = {
    "studio": "Студия",
    "1bed": "1-спальня",
    "2bed": "2-спальни",
    "3bed": "3-спальни",
}

_CITY_DISPLAY: dict[str, str] = {city: city for city in DEMO_CITIES}

# Preference category items for Multiselect widget
_PREF_ITEMS: list[tuple[str, str]] = [
    ("🏢 Этаж", "floor"),
    ("🌅 Вид", "view"),
    ("📐 Площадь", "area"),
    ("🛋 Мебель", "furnished"),
    ("🏷 Акции", "promotion"),
    ("🏘 Комплекс", "complex"),
    ("📍 Секция", "section"),
]

# Widget ID for preferences Multiselect
_PREF_MS_ID = "pref_ms"

_SCROLL_PAGE_SIZE = 10


def format_apartment_list(
    results: list[dict[str, Any]],
    *,
    shown_start: int = 1,
    total: int | None = None,
) -> str:
    """Format apartments as multi-line HTML text for list view mode."""
    parts: list[str] = []

    shown_end = shown_start + len(results) - 1
    if total is not None and len(results) > 0:
        parts.append(f"Найдено <b>{total}</b> апартаментов (показаны {shown_start}–{shown_end})\n")

    for i, apt in enumerate(results):
        p = apt.get("payload", apt)
        rooms_num = p.get("rooms", 1)
        prop_type = _ROOMS_DISPLAY.get(rooms_num, str(rooms_num))
        price_raw = int(p.get("price_eur", 0))
        price_fmt = f"{price_raw:,}".replace(",", " ")

        line1_parts = [f"<b>{shown_start + i}. {p.get('complex_name', '')}</b>"]
        section = p.get("section", "")
        if section:
            line1_parts.append(section)
        apt_num = p.get("apartment_number", "")
        if apt_num:
            line1_parts.append(f"№{apt_num}")

        line2_parts = [prop_type]
        floor = p.get("floor", 0)
        if floor:
            line2_parts.append(f"{floor} эт")
        area = p.get("area_m2", 0)
        if area:
            line2_parts.append(f"{round(area)} м²")
        view = p.get("view_primary", "")
        if view:
            line2_parts.append(_VIEW_DISPLAY.get(view, view))

        line3 = f"<b>{price_fmt} €</b>"

        parts.append(
            " · ".join(line1_parts) + "\n    " + " · ".join(line2_parts) + "\n    " + line3
        )

    return "\n\n".join(parts)


def build_funnel_filters(
    *,
    city: str | None = None,
    rooms: str = "any",
    budget: str = "any",
    complex_name: str | None = None,
    floor: str | None = None,
    view: str | None = None,
    is_furnished: str | None = None,
    is_promotion: str | None = None,
    area: str | None = None,
    section: str | None = None,
) -> dict[str, Any]:
    """Build Qdrant payload filter dict from funnel dialog selections."""
    filters: dict[str, Any] = {}
    if city and city != "any":
        filters["city"] = city
    if rooms in _ROOMS_MAP:
        filters["rooms"] = _ROOMS_MAP[rooms]
    if budget in _BUDGET_MAP:
        filters["price_eur"] = _BUDGET_MAP[budget]
    if complex_name and complex_name != "any":
        filters["complex_name"] = complex_name
    if floor and floor != "any" and floor in _FLOOR_MAP:
        filters["floor"] = _FLOOR_MAP[floor]
    if view and view != "any":
        filters["view_tags"] = [view]
    if is_furnished == "yes":
        filters["is_furnished"] = True
    elif is_furnished == "no":
        filters["is_furnished"] = False
    if is_promotion == "yes":
        filters["is_promotion"] = True
    if area and area != "any" and area in _AREA_MAP:
        filters["area_m2"] = _AREA_MAP[area]
    if section and section != "any":
        filters["section"] = section
    return filters


def _compute_active_pref_categories(data: dict[str, Any]) -> list[str]:
    """Return list of category IDs that have a non-default value set."""
    checked: list[str] = []
    if data.get("floor") and data["floor"] != "any":
        checked.append("floor")
    if data.get("view") and data["view"] != "any":
        checked.append("view")
    if data.get("area") and data["area"] != "any":
        checked.append("area")
    if data.get("is_furnished"):
        checked.append("furnished")
    if data.get("is_promotion"):
        checked.append("promotion")
    if data.get("complex") and data["complex"] != "any":
        checked.append("complex")
    if data.get("section") and data["section"] != "any":
        checked.append("section")
    return checked


def _build_funnel_filters(data: dict[str, Any]) -> dict[str, Any]:
    """Build Qdrant filters from dialog_data dict."""
    return build_funnel_filters(
        city=data.get("city"),
        rooms=data.get("property_type", "any"),
        budget=data.get("budget", "any"),
        complex_name=data.get("complex"),
        floor=data.get("floor"),
        view=data.get("view"),
        is_furnished=data.get("is_furnished"),
        is_promotion=data.get("is_promotion"),
        area=data.get("area"),
        section=data.get("section"),
    )
