"""Filter panel dialog — aiogram-dialog replacement for custom inline filter panel.

Replaces telegram_bot/handlers/filter_panel.py (289 LOC) and
telegram_bot/keyboards/filter_panel.py (290 LOC) with SDK-native
Dialog/Window/Radio/SwitchTo widgets.

Flow:
    CatalogSG.results/empty → manager.start(FilterSG.hub)
    → user selects filters via Windows (Radio widgets with ✓ indicator)
    → on_apply: writes updated catalog_runtime
    → returns to CatalogSG.results or CatalogSG.empty
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, ShowMode, Window
from aiogram_dialog.widgets.kbd import Button, Column, Radio, Row, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.dialogs.catalog import activate_catalog_state, show_catalog_controls
from telegram_bot.dialogs.filter_constants import (
    AREA_OPTIONS,
    BUDGET_OPTIONS,
    CITY_OPTIONS,
    FIELD_TO_FILTER_KEY,
    FLOOR_OPTIONS,
    ROOMS_OPTIONS,
    VIEW_OPTIONS,
    build_filters_dict,
)
from telegram_bot.dialogs.root_nav import get_main_menu_label, root_menu_button
from telegram_bot.dialogs.states import CatalogSG, FilterSG
from telegram_bot.services.catalog_rendering import send_catalog_results
from telegram_bot.services.catalog_session import (
    CATALOG_RUNTIME_DATA_KEY,
    build_catalog_runtime,
)


logger = logging.getLogger(__name__)

# "Любой" option used in every filter sub-menu to clear that filter.
# IMPORTANT: use "any" (not "") — aiogram-dialog widgets skip empty item_ids.
_ANY_OPTION = ("Любой", "any")


def _has_filter_value(value: Any) -> bool:
    """Return True only for meaningful filter values used by the dialog."""
    return value not in (None, "", "any", "None")


def _main_menu_label_for(dialog_manager: DialogManager) -> str:
    """Return main-menu label even when tests provide a minimal dialog_manager stub."""
    middleware = getattr(dialog_manager, "middleware_data", None) or {}
    i18n = middleware.get("i18n") if isinstance(middleware, dict) else None
    return get_main_menu_label(i18n)


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

    from telegram_bot.dialogs.filter_constants import (
        AREA_DISPLAY,
        BUDGET_DISPLAY,
        FLOOR_DISPLAY,
        ROOMS_DISPLAY,
        VIEW_DISPLAY,
    )

    # Build dynamic active filters summary — only show selected (non-default) filters
    lines: list[str] = []

    city_val = dd.get("city")
    if _has_filter_value(city_val):
        lines.append(f"📍 Город: {city_val}")

    rooms_val = dd.get("rooms")
    if _has_filter_value(rooms_val):
        try:
            label = ROOMS_DISPLAY.get(int(rooms_val), str(rooms_val))
        except (ValueError, TypeError):
            label = str(rooms_val)
        lines.append(f"🛏 Комнаты: {label}")

    budget_val = dd.get("budget")
    if _has_filter_value(budget_val):
        lines.append(f"💰 Бюджет: {BUDGET_DISPLAY.get(str(budget_val), str(budget_val))}")

    view_val = dd.get("view")
    if _has_filter_value(view_val):
        lines.append(f"🌅 Вид: {VIEW_DISPLAY.get(view_val, view_val)}")

    area_val = dd.get("area")
    if _has_filter_value(area_val):
        lines.append(f"📐 Площадь: {AREA_DISPLAY.get(area_val, area_val)}")

    floor_val = dd.get("floor")
    if _has_filter_value(floor_val):
        lines.append(f"🏢 Этаж: {FLOOR_DISPLAY.get(floor_val, floor_val)}")

    complex_val = dd.get("complex")
    if _has_filter_value(complex_val):
        lines.append(f"🏘 Комплекс: {complex_val}")

    furnished_val = dd.get("furnished")
    if _has_filter_value(furnished_val):
        label = {"true": "Да", "false": "Нет"}.get(furnished_val, furnished_val)
        lines.append(f"🛋 Мебель: {label}")

    promotion_val = dd.get("promotion")
    if promotion_val == "true":
        lines.append("🏷 Только акции")

    active_filters = "\n".join(lines) if lines else "Фильтры не заданы"

    return {
        "count": count,
        "active_filters": active_filters,
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


# ============================================================
# Individual filter getters
# ============================================================


async def get_city_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "city_options": [_ANY_OPTION, *CITY_OPTIONS],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_rooms_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "rooms_options": [_ANY_OPTION] + [(lbl, str(val)) for lbl, val in ROOMS_OPTIONS],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_budget_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "budget_options": [_ANY_OPTION, *BUDGET_OPTIONS],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_view_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "view_options": [_ANY_OPTION, *VIEW_OPTIONS],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_area_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "area_options": [_ANY_OPTION, *AREA_OPTIONS],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_floor_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "floor_options": [_ANY_OPTION, *FLOOR_OPTIONS],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_complex_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Load complex options from service, fall back to empty list."""
    svc = dialog_manager.middleware_data.get("apartments_service")
    complexes: list[str] = []
    if svc is not None:
        with contextlib.suppress(Exception):
            stats = await svc.get_collection_stats()
            complexes = stats.get("complexes") or []
    options: list[tuple[str, str]] = [_ANY_OPTION] + [(c, c) for c in complexes]
    return {
        "complex_options": options,
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_furnished_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "furnished_options": [("Любое", "any"), ("Да", "true"), ("Нет", "false")],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


async def get_promotion_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "promotion_options": [("Любое", "any"), ("Только акции", "true")],
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


# ============================================================
# Radio on_state_changed handlers — store selection in dialog_data + switch to hub
# ============================================================


def _make_radio_handler(field: str):
    """Factory: returns on_state_changed handler for Radio widget."""

    async def handler(
        callback: CallbackQuery,
        _radio: Any,
        manager: DialogManager,
        item_id: str,
    ) -> None:
        if item_id == "any":
            # "Любой" selected — clear this filter
            manager.dialog_data.pop(field, None)
            manager.dialog_data.pop(FIELD_TO_FILTER_KEY.get(field, field), None)
        else:
            # Store raw item_id string — coercion happens in build_filters_dict
            manager.dialog_data[field] = item_id
        await manager.switch_to(FilterSG.hub)

    handler.__name__ = f"on_radio_{field}"
    return handler


on_radio_city = _make_radio_handler("city")
on_radio_rooms = _make_radio_handler("rooms")
on_radio_budget = _make_radio_handler("budget")
on_radio_view = _make_radio_handler("view")
on_radio_area = _make_radio_handler("area")
on_radio_floor = _make_radio_handler("floor")
on_radio_complex = _make_radio_handler("complex")
on_radio_furnished = _make_radio_handler("furnished")
on_radio_promotion = _make_radio_handler("promotion")


# ============================================================
# Reverse mapping: Qdrant filters → dialog_data field names
# ============================================================


def _filters_to_dialog_data(filters: dict[str, Any]) -> dict[str, Any]:
    """Reverse-map apartment_filters dict to dialog_data string item_ids for Radio widgets."""
    from telegram_bot.dialogs.filter_constants import AREA_MAP, BUDGET_MAP, FLOOR_MAP

    dd: dict[str, Any] = {}
    if filters.get("city"):
        dd["city"] = filters["city"]
    if filters.get("rooms") is not None:
        rooms = filters["rooms"]
        if isinstance(rooms, list):
            # Studio from funnel: [0, 1] → "1" for FilterDialog Radio
            dd["rooms"] = "1"
        else:
            dd["rooms"] = str(rooms)
    if filters.get("price_eur"):
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
        area = filters["area_m2"]
        for key, val in AREA_MAP.items():
            if val == area:
                dd["area"] = key
                break
    if filters.get("floor"):
        floor_val = filters["floor"]
        for key, val in FLOOR_MAP.items():
            if val == floor_val:
                dd["floor"] = key
                break
    if filters.get("complex_name"):
        dd["complex"] = filters["complex_name"]
    if filters.get("is_furnished") is not None:
        dd["furnished"] = str(filters["is_furnished"]).lower()
    if filters.get("is_promotion") is not None:
        dd["promotion"] = str(filters["is_promotion"]).lower()
    return dd


# Map dialog_data field → (radio_widget_id, value_to_str converter)
_FIELD_TO_RADIO_ID: dict[str, str] = {
    "city": "r_city",
    "rooms": "r_rooms",
    "budget": "r_budget",
    "view": "r_view",
    "area": "r_area",
    "floor": "r_floor",
    "complex": "r_complex",
    "furnished": "r_furnished",
    "promotion": "r_promotion",
}


async def on_filter_dialog_start(
    start_data: dict[str, Any] | None,
    manager: DialogManager,
) -> None:
    """Pre-populate dialog_data and Radio checked states from existing filters."""
    filters = (start_data or {}).get("filters") or {}
    dialog_data = _filters_to_dialog_data(filters)
    for field in _FIELD_TO_RADIO_ID:
        manager.dialog_data.pop(field, None)
    manager.dialog_data.update(dialog_data)

    # aiogram-dialog Radio stores selection in widget_data and does not support
    # clearing via set_checked(None): it serializes None to the string "None".
    with contextlib.suppress(Exception):
        widget_data = manager.current_context().widget_data
        for radio_id in _FIELD_TO_RADIO_ID.values():
            widget_data.pop(radio_id, None)

    # Sync Radio widget checked states with dialog_data
    for field, radio_id in _FIELD_TO_RADIO_ID.items():
        value = dialog_data.get(field)
        if value is None:
            continue
        with contextlib.suppress(Exception):
            radio_widget = manager.find(radio_id)
            if radio_widget is not None:
                await radio_widget.set_checked(str(value))


# ============================================================
# on_apply — save filters to FSMContext, done()
# ============================================================


async def on_apply(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Apply filters and return to the catalog dialog flow."""
    state: FSMContext = manager.middleware_data["state"]
    dd = manager.dialog_data
    raw_filters = {k: v for k, v in dd.items() if k in FIELD_TO_FILTER_KEY}
    filters = build_filters_dict(raw_filters)
    fsm_data = await state.get_data()
    current_runtime = (
        fsm_data.get(CATALOG_RUNTIME_DATA_KEY) if isinstance(fsm_data, dict) else {}
    ) or {}

    # Fetch first page with new filters
    svc = manager.middleware_data.get("apartments_service")
    results: list = []
    total_count = 0
    next_start: float | None = None
    page_ids: list[str] | None = None
    if svc is not None:
        with contextlib.suppress(Exception):
            results, total_count, next_start, page_ids = await svc.scroll_with_filters(
                filters=filters,
                limit=10,
            )

    runtime = build_catalog_runtime(
        query=current_runtime.get("query", ""),
        source=current_runtime.get("source", "catalog"),
        filters=filters,
        view_mode=current_runtime.get("view_mode", "cards"),
        results=results,
        total=total_count,
        next_offset=next_start,
        shown_item_ids=page_ids,
        bookmarks_context=bool(current_runtime.get("bookmarks_context", False)),
        origin_context=current_runtime.get("origin_context", {}),
    )
    await state.update_data(**{CATALOG_RUNTIME_DATA_KEY: runtime})

    # Show apartment results respecting view mode
    msg = callback.message
    if not msg:
        return

    # Close the filter shell before handing control back to catalog so users
    # do not interact with a stale filter message after apply.
    manager.show_mode = ShowMode.NO_UPDATE
    await manager.done()
    if hasattr(msg, "delete"):
        with contextlib.suppress(Exception):
            await msg.delete()

    if not results:
        await show_catalog_controls(message=msg, dialog_manager=manager, runtime=runtime)
        await activate_catalog_state(dialog_manager=manager, state=CatalogSG.empty)
        return

    await send_catalog_results(
        message=msg,
        property_bot=manager.middleware_data.get("property_bot"),
        results=results,
        total_count=total_count,
        view_mode=runtime.get("view_mode", "cards"),
        shown_start=1,
        telegram_id=callback.from_user.id if callback.from_user else 0,
    )
    await show_catalog_controls(message=msg, dialog_manager=manager, runtime=runtime)
    await activate_catalog_state(dialog_manager=manager, state=CatalogSG.results)


# ============================================================
# on_reset — clear all filter fields in dialog_data + Radio states
# ============================================================


async def on_reset(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Clear all filters from dialog_data and reset Radio widgets."""
    for field in FIELD_TO_FILTER_KEY:
        manager.dialog_data.pop(field, None)
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
    # Clear Radio widget state directly: aiogram-dialog does not support
    # unchecking Radio via set_checked(None) and stores state in widget_data.
    with contextlib.suppress(Exception):
        widget_data = manager.current_context().widget_data
        for radio_id in _FIELD_TO_RADIO_ID.values():
            widget_data.pop(radio_id, None)


# ============================================================
# Dialog definition — Radio widgets with ✓/○ indicators
# ============================================================

filter_dialog = Dialog(
    # Hub window: filter summary + navigation
    Window(
        Format("🏠 Фильтры поиска\n\n{active_filters}\n\nНайдено: {count} апартаментов"),
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
        root_menu_button(),
        getter=get_hub_data,
        state=FilterSG.hub,
    ),
    # City window — Radio with ✓ indicator + back button
    Window(
        Const("📍 Выберите город:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_city",
                item_id_getter=lambda item: item[1],
                items="city_options",
                on_state_changed=on_radio_city,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_city", state=FilterSG.hub),
        getter=get_city_data,
        state=FilterSG.city,
    ),
    # Rooms window
    Window(
        Const("🛏 Выберите количество комнат:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_rooms",
                item_id_getter=lambda item: item[1],
                items="rooms_options",
                on_state_changed=on_radio_rooms,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_rooms", state=FilterSG.hub),
        getter=get_rooms_data,
        state=FilterSG.rooms,
    ),
    # Budget window
    Window(
        Const("💰 Выберите бюджет:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_budget",
                item_id_getter=lambda item: item[1],
                items="budget_options",
                on_state_changed=on_radio_budget,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_budget", state=FilterSG.hub),
        getter=get_budget_data,
        state=FilterSG.budget,
    ),
    # View window
    Window(
        Const("🌅 Выберите вид:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_view",
                item_id_getter=lambda item: item[1],
                items="view_options",
                on_state_changed=on_radio_view,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_view", state=FilterSG.hub),
        getter=get_view_data,
        state=FilterSG.view,
    ),
    # Area window
    Window(
        Const("📐 Выберите площадь:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_area",
                item_id_getter=lambda item: item[1],
                items="area_options",
                on_state_changed=on_radio_area,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_area", state=FilterSG.hub),
        getter=get_area_data,
        state=FilterSG.area,
    ),
    # Floor window
    Window(
        Const("🏢 Выберите этаж:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_floor",
                item_id_getter=lambda item: item[1],
                items="floor_options",
                on_state_changed=on_radio_floor,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_floor", state=FilterSG.hub),
        getter=get_floor_data,
        state=FilterSG.floor,
    ),
    # Complex window
    Window(
        Const("🏘 Выберите комплекс:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_complex",
                item_id_getter=lambda item: item[1],
                items="complex_options",
                on_state_changed=on_radio_complex,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_complex", state=FilterSG.hub),
        getter=get_complex_data,
        state=FilterSG.complex_name,
    ),
    # Furnished window
    Window(
        Const("🛋 Наличие мебели:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_furnished",
                item_id_getter=lambda item: item[1],
                items="furnished_options",
                on_state_changed=on_radio_furnished,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_furnished", state=FilterSG.hub),
        getter=get_furnished_data,
        state=FilterSG.furnished,
    ),
    # Promotion window
    Window(
        Const("🏷 Акционные предложения:"),
        Column(
            Radio(
                Format("✅ {item[0]}"),
                Format("  ◻️ {item[0]}"),
                id="r_promotion",
                item_id_getter=lambda item: item[1],
                items="promotion_options",
                on_state_changed=on_radio_promotion,
            ),
        ),
        root_menu_button(),
        SwitchTo(Const("← Назад"), id="back_promotion", state=FilterSG.hub),
        getter=get_promotion_data,
        state=FilterSG.promotion,
    ),
    on_start=on_filter_dialog_start,
)
