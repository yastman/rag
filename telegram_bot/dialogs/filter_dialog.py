"""Filter panel dialog — aiogram-dialog replacement for custom inline filter panel.

Replaces telegram_bot/handlers/filter_panel.py (289 LOC) and
telegram_bot/keyboards/filter_panel.py (290 LOC) with SDK-native
Dialog/Window/Select/SwitchTo widgets.

Flow:
    CatalogBrowsingSG.browsing → manager.start(FilterSG.hub)
    → user selects filters via Windows
    → on_apply: saves to FSMContext, manager.done()
    → returns to CatalogBrowsingSG.browsing
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Column, Row, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.dialogs.filter_constants import (
    AREA_OPTIONS,
    BUDGET_OPTIONS,
    CITY_OPTIONS,
    FIELD_TO_FILTER_KEY,
    FLOOR_OPTIONS,
    ROOMS_OPTIONS,
    VIEW_OPTIONS,
    build_filters_dict,
    coerce_filter_value,
)
from telegram_bot.dialogs.states import FilterSG


logger = logging.getLogger(__name__)

# "Любой" option used in every filter sub-menu to clear that filter.
# IMPORTANT: use "any" (not "") — aiogram-dialog Select skips empty item_ids.
_ANY_OPTION = ("Любой", "any")

# ============================================================
# Hub getter
# ============================================================


async def get_hub_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter for the hub window — returns filter options and live count."""
    svc = dialog_manager.middleware_data.get("apartments_service")
    count = 0
    if svc is not None:
        dd = dialog_manager.dialog_data
        raw_filters = {k: v for k, v in dd.items() if k in FIELD_TO_FILTER_KEY}
        filters = build_filters_dict(raw_filters)
        with contextlib.suppress(Exception):
            count = await svc.count_with_filters(filters=filters)

    dd = dialog_manager.dialog_data
    city_val = dd.get("city") or "—"
    rooms_val = dd.get("rooms")
    budget_val = dd.get("budget")

    from telegram_bot.dialogs.filter_constants import BUDGET_DISPLAY, ROOMS_DISPLAY

    rooms_label = (
        ROOMS_DISPLAY.get(int(rooms_val), str(rooms_val)) if rooms_val is not None else "—"
    )
    budget_label = BUDGET_DISPLAY.get(str(budget_val), str(budget_val)) if budget_val else "—"

    return {
        "count": count,
        "city_val": city_val,
        "rooms_val": rooms_label,
        "budget_val": budget_label,
        "city_options": [_ANY_OPTION, *CITY_OPTIONS],
        "budget_options": list(BUDGET_OPTIONS),
        "rooms_options": list(ROOMS_OPTIONS),
    }


# ============================================================
# Individual filter getters
# ============================================================


async def get_city_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"city_options": [_ANY_OPTION, *CITY_OPTIONS]}


async def get_rooms_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"rooms_options": [_ANY_OPTION] + [(lbl, str(val)) for lbl, val in ROOMS_OPTIONS]}


async def get_budget_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"budget_options": [_ANY_OPTION, *BUDGET_OPTIONS]}


async def get_view_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"view_options": [_ANY_OPTION, *VIEW_OPTIONS]}


async def get_area_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"area_options": [_ANY_OPTION, *AREA_OPTIONS]}


async def get_floor_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"floor_options": [_ANY_OPTION, *FLOOR_OPTIONS]}


async def get_complex_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Load complex options from service, fall back to empty list."""
    svc = dialog_manager.middleware_data.get("apartments_service")
    complexes: list[str] = []
    if svc is not None:
        with contextlib.suppress(Exception):
            stats = await svc.get_collection_stats()
            complexes = stats.get("complexes") or []
    options: list[tuple[str, str]] = [_ANY_OPTION] + [(c, c) for c in complexes]
    return {"complex_options": options}


async def get_furnished_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"furnished_options": [("Любое", "any"), ("Да", "true"), ("Нет", "false")]}


async def get_promotion_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {"promotion_options": [("Любое", "any"), ("Только акции", "true")]}


# ============================================================
# on_select_* handlers — store selection in dialog_data
# ============================================================


def _make_select_handler(field: str):
    """Factory: returns an on_click handler that stores selected value in dialog_data."""

    async def handler(
        callback: CallbackQuery,
        widget: Any,
        manager: DialogManager,
        item_id: str,
    ) -> None:
        if item_id == "any":
            # "Любой" selected — clear this filter
            manager.dialog_data.pop(field, None)
            manager.dialog_data.pop(FIELD_TO_FILTER_KEY.get(field, field), None)
        else:
            coerced = coerce_filter_value(field, item_id)
            if coerced is None:
                manager.dialog_data.pop(field, None)
                manager.dialog_data.pop(FIELD_TO_FILTER_KEY.get(field, field), None)
            else:
                manager.dialog_data[field] = coerced
        await manager.switch_to(FilterSG.hub)

    handler.__name__ = f"on_select_{field}"
    return handler


def _filters_to_dialog_data(filters: dict[str, Any]) -> dict[str, Any]:
    """Reverse-map apartment_filters dict to dialog_data field names."""
    from telegram_bot.dialogs.filter_constants import BUDGET_MAP

    dd: dict[str, Any] = {}
    if filters.get("city"):
        dd["city"] = filters["city"]
    if filters.get("rooms") is not None:
        dd["rooms"] = filters["rooms"]
    if filters.get("price_eur"):
        # Reverse-lookup budget key from BUDGET_MAP
        price = filters["price_eur"]
        for key, val in BUDGET_MAP.items():
            if val == price:
                dd["budget"] = key
                break
    if filters.get("view_tags"):
        tags = filters["view_tags"]
        if isinstance(tags, list) and tags:
            dd["view"] = tags[0]
    if filters.get("area_m2"):
        dd["area"] = filters["area_m2"]
    if filters.get("floor"):
        dd["floor"] = filters["floor"]
    if filters.get("complex_name"):
        dd["complex"] = filters["complex_name"]
    if filters.get("is_furnished") is not None:
        dd["furnished"] = filters["is_furnished"]
    if filters.get("is_promotion") is not None:
        dd["promotion"] = filters["is_promotion"]
    return dd


async def on_filter_dialog_start(
    start_data: dict[str, Any] | None,
    manager: DialogManager,
) -> None:
    """Pre-populate dialog_data from existing apartment_filters on dialog start."""
    if not start_data:
        return
    filters = start_data.get("filters") or {}
    dialog_data = _filters_to_dialog_data(filters)
    manager.dialog_data.update(dialog_data)


on_select_city = _make_select_handler("city")
on_select_rooms = _make_select_handler("rooms")
on_select_budget = _make_select_handler("budget")
on_select_view = _make_select_handler("view")
on_select_area = _make_select_handler("area")
on_select_floor = _make_select_handler("floor")
on_select_complex = _make_select_handler("complex")
on_select_furnished = _make_select_handler("furnished")
on_select_promotion = _make_select_handler("promotion")


# ============================================================
# on_apply — save filters to FSMContext, done()
# ============================================================


async def on_apply(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Apply current filters: write to FSMContext, reset pagination, close dialog."""
    state: FSMContext = manager.middleware_data["state"]
    dd = manager.dialog_data
    raw_filters = {k: v for k, v in dd.items() if k in FIELD_TO_FILTER_KEY or k == "city"}
    filters = build_filters_dict(raw_filters)
    await state.update_data(
        apartment_filters=filters,
        apartment_offset=0,
        apartment_next_offset=None,
        apartment_scroll_seen_ids=None,
    )
    await manager.done()


# ============================================================
# on_reset — clear all filter fields in dialog_data
# ============================================================


async def on_reset(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Clear all filters from dialog_data."""
    for field in FIELD_TO_FILTER_KEY:
        manager.dialog_data.pop(field, None)
    # Also clear direct filter keys
    for key in (
        "city",
        "rooms",
        "budget",
        "view",
        "area",
        "floor",
        "complex",
        "furnished",
        "promotion",
    ):
        manager.dialog_data.pop(key, None)


# ============================================================
# Dialog definition
# ============================================================

filter_dialog = Dialog(
    # Hub window: filter summary + navigation
    Window(
        Format(
            "🏠 Фильтры поиска\n\n"
            "📍 Город: {city_val}\n"
            "🛏 Комнаты: {rooms_val}\n"
            "💰 Бюджет: {budget_val}\n\n"
            "Найдено: {count} апартаментов"
        ),
        Row(
            SwitchTo(Const("📍 Город"), id="sw_city", state=FilterSG.city),
            SwitchTo(Const("🛏 Комнаты"), id="sw_rooms", state=FilterSG.rooms),
            SwitchTo(Const("💰 Бюджет"), id="sw_budget", state=FilterSG.budget),
        ),
        Row(
            SwitchTo(Const("🌅 Вид"), id="sw_view", state=FilterSG.view),
            SwitchTo(Const("📐 Площадь"), id="sw_area", state=FilterSG.area),
            SwitchTo(Const("🏢 Этаж"), id="sw_floor", state=FilterSG.floor),
        ),
        Row(
            SwitchTo(Const("🏘 Комплекс"), id="sw_complex", state=FilterSG.complex_name),
            SwitchTo(Const("🛋 Мебель"), id="sw_furnished", state=FilterSG.furnished),
            SwitchTo(Const("🏷 Акции"), id="sw_promotion", state=FilterSG.promotion),
        ),
        Row(
            Button(
                Format("✅ Применить ({count})"),
                id="btn_apply",
                on_click=on_apply,
            ),
            Button(
                Const("🗑 Сбросить"),
                id="btn_reset",
                on_click=on_reset,
            ),
        ),
        getter=get_hub_data,
        state=FilterSG.hub,
    ),
    # City window
    Window(
        Const("📍 Выберите город:"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="s_city",
                item_id_getter=lambda item: item[1],
                items="city_options",
                on_click=on_select_city,
            ),
            id="sg_city",
            width=1,
            height=10,
        ),
        getter=get_city_data,
        state=FilterSG.city,
    ),
    # Rooms window
    Window(
        Const("🛏 Выберите количество комнат:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_rooms",
                item_id_getter=lambda item: item[1],
                items="rooms_options",
                on_click=on_select_rooms,
            ),
        ),
        getter=get_rooms_data,
        state=FilterSG.rooms,
    ),
    # Budget window
    Window(
        Const("💰 Выберите бюджет:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_budget",
                item_id_getter=lambda item: item[1],
                items="budget_options",
                on_click=on_select_budget,
            ),
        ),
        getter=get_budget_data,
        state=FilterSG.budget,
    ),
    # View window
    Window(
        Const("🌅 Выберите вид:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_view",
                item_id_getter=lambda item: item[1],
                items="view_options",
                on_click=on_select_view,
            ),
        ),
        getter=get_view_data,
        state=FilterSG.view,
    ),
    # Area window
    Window(
        Const("📐 Выберите площадь:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_area",
                item_id_getter=lambda item: item[1],
                items="area_options",
                on_click=on_select_area,
            ),
        ),
        getter=get_area_data,
        state=FilterSG.area,
    ),
    # Floor window
    Window(
        Const("🏢 Выберите этаж:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_floor",
                item_id_getter=lambda item: item[1],
                items="floor_options",
                on_click=on_select_floor,
            ),
        ),
        getter=get_floor_data,
        state=FilterSG.floor,
    ),
    # Complex window
    Window(
        Const("🏘 Выберите комплекс:"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="s_complex",
                item_id_getter=lambda item: item[1],
                items="complex_options",
                on_click=on_select_complex,
            ),
            id="sg_complex",
            width=1,
            height=8,
        ),
        getter=get_complex_data,
        state=FilterSG.complex_name,
    ),
    # Furnished window
    Window(
        Const("🛋 Наличие мебели:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_furnished",
                item_id_getter=lambda item: item[1],
                items="furnished_options",
                on_click=on_select_furnished,
            ),
        ),
        getter=get_furnished_data,
        state=FilterSG.furnished,
    ),
    # Promotion window
    Window(
        Const("🏷 Акционные предложения:"),
        Column(
            Select(
                Format("{item[0]}"),
                id="s_promotion",
                item_id_getter=lambda item: item[1],
                items="promotion_options",
                on_click=on_select_promotion,
            ),
        ),
        getter=get_promotion_data,
        state=FilterSG.promotion,
    ),
    on_start=on_filter_dialog_start,
)
