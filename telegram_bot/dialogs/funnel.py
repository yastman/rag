"""Property search funnel dialog (aiogram-dialog) — #628, refactored #697."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import operator
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import (
    Back,
    Button,
    Cancel,
    Column,
    ManagedMultiselect,
    Multiselect,
    Row,
    Select,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Format

from telegram_bot.observability import observe

from .states import FunnelSG


# --- Constants ---

_CITY_OPTIONS: list[tuple[str, str]] = [
    ("Солнечный берег", "Солнечный берег"),
    ("Свети Влас", "Свети Влас"),
    ("Элените", "Элените"),
    ("Любой город", "any"),
]

_COMPLEX_OPTIONS: list[tuple[str, str]] = [
    ("Crown Fort Club", "Crown Fort Club"),
    ("Green Fort Suites", "Green Fort Suites"),
    ("Imperial Fort Club", "Imperial Fort Club"),
    ("Marina View Fort Beach", "Marina View Fort Beach"),
    ("Messambria Fort Beach", "Messambria Fort Beach"),
    ("Nessebar Fort Residence", "Nessebar Fort Residence"),
    ("Panorama Fort Beach", "Panorama Fort Beach"),
    ("Premier Fort Beach", "Premier Fort Beach"),
    ("Premier Fort Suites", "Premier Fort Suites"),
    ("Prestige Fort Beach", "Prestige Fort Beach"),
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

_ROOMS_MAP: dict[str, int | list[int]] = {"studio": [0, 1], "1bed": 2, "2bed": 3, "3bed": 4}
_PROPERTY_TYPE_QUERY_TEXT: dict[str, str] = {
    "studio": "студия",
    "1bed": "1 спальня",
    "2bed": "2 спальни",
    "3bed": "3 спальни",
}

_BUDGET_MAP: dict[str, dict[str, int]] = {
    "low": {"lte": 50000},
    "mid": {"gte": 50000, "lte": 100000},
    "high": {"gte": 100000, "lte": 150000},
    "premium": {"gte": 150000, "lte": 200000},
    "luxury": {"gte": 200000},
}

_FLOOR_MAP: dict[str, dict[str, int]] = {
    "low": {"gte": 0, "lte": 1},
    "mid": {"gte": 2, "lte": 3},
    "high": {"gte": 4, "lte": 5},
    "top": {"gte": 6},
}

_AREA_MAP: dict[str, dict[str, int]] = {
    "small": {"lte": 40},
    "mid": {"gte": 40, "lte": 60},
    "large": {"gte": 60, "lte": 80},
    "xlarge": {"gte": 80, "lte": 120},
    "xxlarge": {"gte": 120},
}

_ROOMS_DISPLAY: dict[int, str] = {
    0: "Студия",
    1: "Студия",
    2: "1-спальня",
    3: "2-спальни",
    4: "3-спальни",
}

# Display labels for summary
_BUDGET_DISPLAY: dict[str, str] = {
    "low": "До 50 000 €",
    "mid": "50 000 – 100 000 €",
    "high": "100 000 – 150 000 €",
    "premium": "150 000 – 200 000 €",
    "luxury": "Более 200 000 €",
}

_FLOOR_DISPLAY: dict[str, str] = {
    "low": "0-1 этаж",
    "mid": "2-3 этаж",
    "high": "4-5 этаж",
    "top": "6+ этаж",
}

_AREA_DISPLAY: dict[str, str] = {
    "small": "До 40 m²",
    "mid": "40–60 m²",
    "large": "60–80 m²",
    "xlarge": "80–120 m²",
    "xxlarge": "120+ m²",
}

_VIEW_DISPLAY: dict[str, str] = {
    "sea": "Море",
    "sea_panorama": "Панорама моря",
    "ultra_sea_panorama": "Ультра панорама моря",
    "ultra_sea": "Ультра море",
    "pool": "Бассейн",
    "garden": "Газон/сад",
    "forest": "Лес/горы",
}

_PROPERTY_TYPE_DISPLAY: dict[str, str] = {
    "studio": "Студия",
    "1bed": "1-спальня",
    "2bed": "2-спальни",
    "3bed": "3-спальни",
}

_CITY_DISPLAY: dict[str, str] = {
    "Солнечный берег": "Солнечный берег",
    "Свети Влас": "Свети Влас",
    "Элените": "Элените",
}


def format_apartment_list(results: list[dict[str, Any]], *, shown_start: int = 1) -> str:
    """Format apartments as compact HTML text for list view mode."""
    lines: list[str] = []
    for i, apt in enumerate(results):
        p = apt.get("payload", apt)
        rooms_num = p.get("rooms", 1)
        prop_type = _ROOMS_DISPLAY.get(rooms_num, str(rooms_num))
        price_raw = int(p.get("price_eur", 0))
        price_fmt = f"{price_raw:,}".replace(",", " ")

        parts = [f"<b>{shown_start + i}. {p.get('complex_name', '')}</b>"]
        section = p.get("section", "")
        if section:
            parts.append(section)
        apt_num = p.get("apartment_number", "")
        if apt_num:
            parts.append(f"№{apt_num}")
        parts.append(prop_type)
        floor = p.get("floor", 0)
        if floor:
            parts.append(f"{floor} эт")
        area = p.get("area_m2", 0)
        if area:
            parts.append(f"{round(area)} м²")
        view = p.get("view_primary", "")
        if view:
            parts.append(_VIEW_DISPLAY.get(view, view))
        parts.append(f"<b>{price_fmt} €</b>")

        lines.append(" · ".join(parts))
    return "\n".join(lines)


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


logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


async def _persist_funnel_lead_score_safe(**kwargs: Any) -> None:
    """Persist/sync funnel score without breaking callback flow."""
    try:
        from telegram_bot.services.funnel_lead_scoring import persist_and_sync_funnel_lead_score

        await persist_and_sync_funnel_lead_score(**kwargs)
    except Exception:
        logger.exception("Failed to persist/sync funnel lead score")


def _spawn_persist_funnel_lead_score(**kwargs: Any) -> None:
    """Run heavy side effects in the background to keep callback responsive."""
    task = asyncio.create_task(_persist_funnel_lead_score_safe(**kwargs))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


# --- Getters (provide data to windows) ---


async def get_city_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for city/resort selection (Step 1)."""
    dialog_manager = kwargs.get("dialog_manager")
    middleware = getattr(dialog_manager, "middleware_data", None) or kwargs.get(
        "middleware_data", {}
    )
    i18n = middleware.get("i18n")
    btn_back = i18n.get("back") if i18n else "Назад"

    svc = middleware.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            cities = await svc.get_distinct_values("city")
            items = [(c, c) for c in cities]
        except Exception:
            logger.warning("Failed to load dynamic cities, using fallback")
            items = list(_CITY_OPTIONS[:-1])
    else:
        items = list(_CITY_OPTIONS[:-1])

    items.append(("Любой город", "any"))
    return {
        "title": "Выберите город:",
        "items": items,
        "btn_back": btn_back,
    }


async def get_property_types(**kwargs: Any) -> dict[str, Any]:
    """Getter for property type selection."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Студия", "studio"),
        ("1-спальня", "1bed"),
        ("2-спальни", "2bed"),
        ("3-спальни", "3bed"),
        ("Любой тип", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Какой тип жилья?", "items": items, "btn_back": btn_back}


async def get_budget_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for budget selection."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("До 50 000 €", "low"),
        ("50 000 – 100 000 €", "mid"),
        ("100 000 – 150 000 €", "high"),
        ("150 000 – 200 000 €", "premium"),
        ("Более 200 000 €", "luxury"),
        ("Любой бюджет", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "Назад"
    return {"title": "Какой бюджет?", "items": items, "btn_back": btn_back}


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


async def get_preferences_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for preferences multi-select menu (Step 4).

    Syncs Multiselect widget state from dialog_data so checkmarks reflect
    actual selections. The "done" button is a separate Button widget.
    """
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    dialog_manager = kwargs.get("dialog_manager")
    data: dict[str, Any] = {}
    if dialog_manager is not None:
        data = getattr(dialog_manager, "dialog_data", {})

    btn_back = i18n.get("back") if i18n else "Назад"

    # Sync Multiselect widget state from dialog_data
    if dialog_manager is not None:
        with contextlib.suppress(AttributeError):
            dialog_manager.current_context().widget_data[_PREF_MS_ID] = (
                _compute_active_pref_categories(data)
            )

    return {
        "title": "✨ Есть ли дополнительные пожелания?",
        "items": _PREF_ITEMS,
        "btn_back": btn_back,
    }


async def get_pref_floor_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for floor sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("0-1 этаж", "low"),
        ("2-3 этаж", "mid"),
        ("4-5 этаж", "high"),
        ("6+ этаж", "top"),
        ("Любой этаж", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {"title": "Какой этаж предпочитаете?", "items": items, "btn_back": btn_back}


async def get_pref_view_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for view sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Море", "sea"),
        ("Бассейн", "pool"),
        ("Газон/сад", "garden"),
        ("Лес/горы", "forest"),
        ("Любой вид", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {"title": "Какой вид предпочитаете?", "items": items, "btn_back": btn_back}


async def get_pref_furnished_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for furnished sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("С мебелью", "yes"),
        ("Без мебели", "no"),
        ("Не важно", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {"title": "Меблировка:", "items": items, "btn_back": btn_back}


async def get_pref_promotion_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for promotion sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("Только акции", "yes"),
        ("Неважно", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {"title": "Специальные акции:", "items": items, "btn_back": btn_back}


async def get_pref_area_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for area sub-options."""
    i18n = kwargs.get("middleware_data", {}).get("i18n")
    items = [
        ("До 40 m²", "small"),
        ("40–60 m²", "mid"),
        ("60–80 m²", "large"),
        ("80–120 m²", "xlarge"),
        ("120+ m²", "xxlarge"),
        ("Любая площадь", "any"),
    ]
    btn_back = i18n.get("back") if i18n else "← Назад"
    return {"title": "Какую площадь предпочитаете?", "items": items, "btn_back": btn_back}


async def get_pref_complex_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for complex sub-options in preferences."""
    dialog_manager = kwargs.get("dialog_manager")
    middleware = getattr(dialog_manager, "middleware_data", None) or kwargs.get(
        "middleware_data", {}
    )
    i18n = middleware.get("i18n")
    btn_back = i18n.get("back") if i18n else "← Назад"

    svc = middleware.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            complexes = await svc.get_distinct_values("complex_name")
            items = [(c, c) for c in complexes]
        except Exception:
            logger.warning("Failed to load dynamic complexes, using fallback")
            items = list(_COMPLEX_OPTIONS[:-1])
    else:
        items = list(_COMPLEX_OPTIONS[:-1])

    items.append(("Любой комплекс", "any"))
    return {"title": "Выберите комплекс:", "items": items, "btn_back": btn_back}


async def get_pref_section_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for section sub-options in preferences."""
    dialog_manager = kwargs.get("dialog_manager")
    middleware = getattr(dialog_manager, "middleware_data", None) or kwargs.get(
        "middleware_data", {}
    )
    i18n = middleware.get("i18n")
    btn_back = i18n.get("back") if i18n else "← Назад"

    svc = middleware.get("apartments_service")
    items: list[tuple[str, str]]
    if svc is not None:
        try:
            sections = await svc.get_distinct_values("section")
            items = [(s, s) for s in sections]
        except Exception:
            logger.warning("Failed to load dynamic sections, using fallback")
            items = list(_SECTION_OPTIONS[:-1])
    else:
        items = list(_SECTION_OPTIONS[:-1])

    items.append(("Любая секция", "any"))
    return {"title": "Выберите секцию:", "items": items, "btn_back": btn_back}


async def get_summary_data(**kwargs: Any) -> dict[str, Any]:
    """Getter for summary window — shows selected filters and can_search flag."""
    dialog_manager = kwargs.get("dialog_manager")
    data: dict[str, Any] = {}
    if dialog_manager is not None:
        data = getattr(dialog_manager, "dialog_data", {})
        # Populate dialog_data from start_data (when returning from catalog filters)
        start = getattr(dialog_manager, "start_data", None) or {}
        if start and not data:
            data.update(start)

    lines: list[str] = ["Ваши параметры поиска:\n"]

    city_val = data.get("city", "any")
    city_label = city_val if city_val and city_val != "any" else "Любой"
    lines.append(f"🏙 Город: {city_label}")

    complex_val = data.get("complex")
    if complex_val and complex_val != "any":
        lines.append(f"🏢 Комплекс: {complex_val}")

    property_type_val = data.get("property_type", "any")
    property_type_label = (
        _PROPERTY_TYPE_DISPLAY.get(property_type_val, property_type_val)
        if property_type_val and property_type_val != "any"
        else "Любой"
    )
    lines.append(f"🏠 Тип: {property_type_label}")

    budget_val = data.get("budget", "any")
    budget_label = (
        _BUDGET_DISPLAY.get(budget_val, budget_val)
        if budget_val and budget_val != "any"
        else "Любой"
    )
    lines.append(f"💰 Бюджет: {budget_label}")

    floor_val = data.get("floor")
    if floor_val and floor_val != "any":
        lines.append(f"🏗 Этаж: {_FLOOR_DISPLAY.get(floor_val, floor_val)}")

    view_val = data.get("view")
    if view_val and view_val != "any":
        lines.append(f"🌅 Вид: {_VIEW_DISPLAY.get(view_val, view_val)}")

    area_val = data.get("area")
    if area_val and area_val != "any":
        lines.append(f"📐 Площадь: {_AREA_DISPLAY.get(area_val, area_val)}")

    section_val = data.get("section")
    if section_val and section_val != "any":
        lines.append(f"📍 Секция: {section_val}")

    furnished_val = data.get("is_furnished")
    if furnished_val == "yes":
        lines.append("🛋 Меблировка: С мебелью")
    elif furnished_val == "no":
        lines.append("🛋 Меблировка: Без мебели")

    promotion_val = data.get("is_promotion")
    if promotion_val == "yes":
        lines.append("🎁 Акции: Только акции")

    summary_text = "\n".join(lines)

    # Live count via payload filter
    svc = None
    if dialog_manager is not None:
        middleware = getattr(dialog_manager, "middleware_data", {})
        svc = middleware.get("apartments_service")
    count = 0
    if svc is not None:
        try:
            filters = _build_funnel_filters(data)
            count = await svc.count_with_filters(filters=filters)
        except Exception:
            logger.exception("Failed to count apartments for summary")
    summary_text += f"\n\nНайдено: {count} апартаментов\nСортировка: по цене ↑"

    return {
        "summary_text": summary_text,
        "can_search": True,
    }


async def get_change_filter_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for change-filter selection window."""
    items = [
        ("Город", "city"),
        ("Тип жилья", "property_type"),
        ("Бюджет", "budget"),
    ]
    return {"title": "Что хотите изменить?", "items": items, "btn_back": "← Назад"}


_SCROLL_PAGE_SIZE = 10


# --- Handlers (on_click) ---


async def on_city_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save city selection and advance to property type."""
    manager.dialog_data["city"] = item_id
    if manager.dialog_data.pop("_return_to_summary", False):
        await manager.switch_to(FunnelSG.summary)
    else:
        await manager.switch_to(FunnelSG.property_type)


async def on_property_type_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save property type and advance to budget."""
    manager.dialog_data["property_type"] = item_id
    if manager.dialog_data.pop("_return_to_summary", False):
        await manager.switch_to(FunnelSG.summary)
    else:
        await manager.switch_to(FunnelSG.budget)


async def on_budget_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save budget and advance to preferences."""
    manager.dialog_data["budget"] = item_id
    if manager.dialog_data.pop("_return_to_summary", False):
        await manager.switch_to(FunnelSG.summary)
    else:
        await manager.switch_to(FunnelSG.preferences)


async def on_pref_done(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Proceed to summary from preferences menu."""
    await manager.switch_to(FunnelSG.summary)


async def on_pref_category_selected(
    callback: CallbackQuery,
    widget: ManagedMultiselect,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Route to the appropriate sub-option window."""
    _PREF_STATE_MAP = {
        "floor": FunnelSG.pref_floor,
        "view": FunnelSG.pref_view,
        "area": FunnelSG.pref_area,
        "furnished": FunnelSG.pref_furnished,
        "promotion": FunnelSG.pref_promotion,
        "complex": FunnelSG.pref_complex,
        "section": FunnelSG.pref_section,
    }
    target = _PREF_STATE_MAP.get(item_id)
    if target:
        await manager.switch_to(target)


async def on_pref_floor_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save floor preference and return to preferences menu."""
    manager.dialog_data["floor"] = item_id
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_view_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save view preference and return to preferences menu."""
    manager.dialog_data["view"] = item_id
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_furnished_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save furnished preference and return to preferences menu."""
    manager.dialog_data["is_furnished"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_promotion_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save promotion preference and return to preferences menu."""
    manager.dialog_data["is_promotion"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_area_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save area preference and return to preferences menu."""
    manager.dialog_data["area"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_complex_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save complex preference and return to preferences menu."""
    manager.dialog_data["complex"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


async def on_pref_section_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save section preference and return to preferences menu."""
    manager.dialog_data["section"] = item_id if item_id != "any" else None
    await manager.switch_to(FunnelSG.preferences)


@observe(name="dialog-funnel-search", capture_input=False, capture_output=False)
async def on_summary_search(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Search, send photo cards, close dialog, show catalog keyboard."""
    from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

    data = manager.dialog_data
    data.pop("scroll_start_from", None)
    data.pop("scroll_seen_ids", None)
    data["scroll_page"] = 1

    # Persist lead score (fire-and-forget)
    try:
        from telegram_bot.bot import make_session_id

        if callback.from_user is not None:
            _spawn_persist_funnel_lead_score(
                telegram_user_id=callback.from_user.id,
                session_id=make_session_id("chat", callback.message.chat.id)
                if callback.message is not None
                else make_session_id("chat", callback.from_user.id),
                property_type=data.get("property_type"),
                budget=data.get("budget"),
                timeline=None,
                user_service=manager.middleware_data.get("user_service"),
                pg_pool=manager.middleware_data.get("pg_pool"),
                lead_scoring_store=manager.middleware_data.get("lead_scoring_store"),
                kommo_client=manager.middleware_data.get("kommo_client"),
                hot_lead_notifier=manager.middleware_data.get("hot_lead_notifier"),
                config=manager.middleware_data.get("bot_config"),
            )
    except Exception:
        logger.exception("Failed to schedule funnel lead score persistence")

    # Resolve services
    svc = manager.middleware_data.get("apartments_service")
    property_bot = manager.middleware_data.get("property_bot")
    if svc is None and property_bot is not None:
        svc = getattr(property_bot, "_apartments_service", None)

    if svc is None or callback.message is None:
        await manager.done()
        return

    # Search
    try:
        filters = _build_funnel_filters(data)
        results, total_count, _next_start, _page_ids = await svc.scroll_with_filters(
            filters=filters,
            limit=_SCROLL_PAGE_SIZE,
            start_from=None,
        )
    except Exception:
        logger.exception("Failed to fetch funnel results")
        await manager.done()
        return

    # Close dialog before sending cards
    await manager.done()

    # Determine view mode from button id
    view_mode = "list" if button.widget_id == "search_list" else "cards"

    # Store results in FSMContext for pagination
    state = manager.middleware_data.get("state")
    if state is not None:
        await state.update_data(
            apartment_results=results,
            apartment_query=f"funnel:{data.get('city', 'any')}",
            apartment_offset=len(results),
            bookmarks_context=False,
            apartment_total=total_count,
            apartment_next_offset=_next_start,
            apartment_scroll_seen_ids=_page_ids,
            apartment_filters=filters,
            funnel_data=dict(data),
            catalog_mode=True,
            catalog_view_mode=view_mode,
        )

    if not results:
        await callback.message.answer(
            "К сожалению, по вашим критериям ничего не найдено.\n"
            "Попробуйте изменить параметры поиска."
        )
        return

    if view_mode == "list":
        # Send compact text list as one message
        text = format_apartment_list(results, shown_start=1)
        await callback.message.answer(text, parse_mode="HTML")
    else:
        # Send photo cards
        if property_bot is not None:
            for result in results:
                telegram_id = callback.from_user.id if callback.from_user else 0
                await property_bot._send_property_card(callback.message, result, telegram_id)

    # Catalog keyboard (счётчик на кнопке — без дублирующего текста)
    shown = len(results)
    catalog_kb = build_catalog_keyboard(shown=shown, total=total_count)
    await callback.message.answer("📋 Каталог", reply_markup=catalog_kb)


async def on_change_filter_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Set return-to-summary flag and jump to selected step for editing."""
    manager.dialog_data["_return_to_summary"] = True
    _CHANGE_STATE_MAP = {
        "city": FunnelSG.city,
        "property_type": FunnelSG.property_type,
        "budget": FunnelSG.budget,
    }
    target = _CHANGE_STATE_MAP.get(item_id, FunnelSG.summary)
    await manager.switch_to(target)


async def on_zero_suggestion_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Apply zero-results recovery suggestion and refresh results/new search."""
    data = manager.dialog_data

    if item_id == "rm_floor":
        data.pop("floor", None)
    elif item_id == "rm_view":
        data.pop("view", None)
    elif item_id == "rm_furnished":
        data.pop("is_furnished", None)
    elif item_id == "rm_promotion":
        data.pop("is_promotion", None)
    elif item_id == "rm_area":
        data.pop("area", None)
    elif item_id == "rm_section":
        data.pop("section", None)
    elif item_id == "rm_budget":
        data["budget"] = "any"
    elif item_id == "new_search":
        for key in (
            "city",
            "complex",
            "property_type",
            "budget",
            "floor",
            "view",
            "area",
            "section",
            "is_furnished",
            "is_promotion",
            "scroll_start_from",
            "scroll_seen_ids",
            "scroll_page",
        ):
            data.pop(key, None)
        await manager.switch_to(FunnelSG.city)
        return
    else:
        return

    data.pop("scroll_start_from", None)
    data.pop("scroll_seen_ids", None)
    data["scroll_page"] = 1
    await manager.switch_to(FunnelSG.summary)


# --- Dialog ---


funnel_dialog = Dialog(
    # Step 1: City selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="city",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_city_selected,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_city_options,
        state=FunnelSG.city,
    ),
    # Step 2: Property type
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="property_type",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_property_type_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_property_types,
        state=FunnelSG.property_type,
    ),
    # Step 3: Budget
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="budget",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_budget_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_budget_options,
        state=FunnelSG.budget,
    ),
    # Step 4: Preferences multi-select menu
    Window(
        Format("{title}"),
        Column(
            Multiselect(
                checked_text=Format("✓ {item[0]}"),
                unchecked_text=Format("{item[0]}"),
                id=_PREF_MS_ID,
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_category_selected,
            ),
        ),
        Button(
            Format("▶️ Нет, перейти к результатам"),
            id="pref_done",
            on_click=on_pref_done,
        ),
        Back(Format("{btn_back}")),
        getter=get_preferences_options,
        state=FunnelSG.preferences,
    ),
    # Step 4a: Floor sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_floor",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_floor_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_floor_back", state=FunnelSG.preferences),
        getter=get_pref_floor_options,
        state=FunnelSG.pref_floor,
    ),
    # Step 4b: View sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_view",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_view_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_view_back", state=FunnelSG.preferences),
        getter=get_pref_view_options,
        state=FunnelSG.pref_view,
    ),
    # Step 4c: Furnished sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_furnished",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_furnished_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_furn_back", state=FunnelSG.preferences),
        getter=get_pref_furnished_options,
        state=FunnelSG.pref_furnished,
    ),
    # Step 4d: Promotion sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_promotion",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_promotion_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_promo_back", state=FunnelSG.preferences),
        getter=get_pref_promotion_options,
        state=FunnelSG.pref_promotion,
    ),
    # Step 4f: Area sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_area",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_area_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_area_back", state=FunnelSG.preferences),
        getter=get_pref_area_options,
        state=FunnelSG.pref_area,
    ),
    # Step 4e: Complex sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_complex",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_complex_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_cplx_back", state=FunnelSG.preferences),
        getter=get_pref_complex_options,
        state=FunnelSG.pref_complex,
    ),
    # Step 4g: Section sub-options
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="pref_section",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_pref_section_selected,
            ),
        ),
        SwitchTo(Format("{btn_back}"), id="pref_section_back", state=FunnelSG.preferences),
        getter=get_pref_section_options,
        state=FunnelSG.pref_section,
    ),
    # Step 5: Summary + confirmation
    Window(
        Format("{summary_text}"),
        Row(
            Button(
                Format("📋 Списком"),
                id="search_list",
                on_click=on_summary_search,
                when="can_search",
            ),
            Button(
                Format("🏠 Карточками"),
                id="search_cards",
                on_click=on_summary_search,
                when="can_search",
            ),
        ),
        Row(
            SwitchTo(
                Format("✏️ Изменить"),
                id="change",
                state=FunnelSG.change_filter,
            ),
            Cancel(Format("Отмена")),
        ),
        getter=get_summary_data,
        state=FunnelSG.summary,
    ),
    # Step 5a: Change filter selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="change_filter",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_change_filter_selected,
            ),
        ),
        Back(Format("{btn_back}")),
        getter=get_change_filter_options,
        state=FunnelSG.change_filter,
    ),
)
