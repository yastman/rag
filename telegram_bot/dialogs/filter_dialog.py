"""Filter panel dialog — aiogram-dialog replacement for custom inline filter panel.

Replaces telegram_bot/handlers/filter_panel.py (289 LOC) and
telegram_bot/keyboards/filter_panel.py (290 LOC) with SDK-native
Dialog/Window/Radio/SwitchTo widgets.

Flow:
    CatalogBrowsingSG.browsing → manager.start(FilterSG.hub)
    → user selects filters via Windows (Radio widgets with ✓ indicator)
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
from aiogram_dialog.widgets.kbd import Button, Column, Radio, Row, SwitchTo
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
)
from telegram_bot.dialogs.states import FilterSG


logger = logging.getLogger(__name__)

# "Любой" option used in every filter sub-menu to clear that filter.
# IMPORTANT: use "any" (not "") — aiogram-dialog widgets skip empty item_ids.
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
    city_val = dd.get("city") or "Любой"
    rooms_val = dd.get("rooms")
    budget_val = dd.get("budget")

    from telegram_bot.dialogs.filter_constants import BUDGET_DISPLAY, ROOMS_DISPLAY

    rooms_label = "Любой"
    if rooms_val is not None:
        try:
            rooms_label = ROOMS_DISPLAY.get(int(rooms_val), str(rooms_val))
        except (ValueError, TypeError):
            rooms_label = str(rooms_val)
    budget_label = BUDGET_DISPLAY.get(str(budget_val), str(budget_val)) if budget_val else "Любой"

    return {
        "count": count,
        "city_val": city_val,
        "rooms_val": rooms_label,
        "budget_val": budget_label,
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
# Radio on_state_changed handlers — store selection in dialog_data + switch to hub
# ============================================================


def _make_radio_handler(field: str):
    """Factory: returns on_state_changed handler for Radio widget."""

    async def handler(
        callback: CallbackQuery,
        radio: Any,
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
        dd["rooms"] = str(filters["rooms"])
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
    if not start_data:
        return
    filters = start_data.get("filters") or {}
    dialog_data = _filters_to_dialog_data(filters)
    manager.dialog_data.update(dialog_data)

    # Sync Radio widget checked states with dialog_data
    for field, radio_id in _FIELD_TO_RADIO_ID.items():
        value = dialog_data.get(field)
        if value is not None:
            with contextlib.suppress(Exception):
                radio_widget = manager.find(radio_id)
                await radio_widget.set_checked(str(value))


# ============================================================
# on_apply — save filters to FSMContext, done()
# ============================================================


async def on_apply(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Apply current filters: fetch first page, show cards, close dialog."""
    state: FSMContext = manager.middleware_data["state"]
    dd = manager.dialog_data
    raw_filters = {k: v for k, v in dd.items() if k in FIELD_TO_FILTER_KEY}
    filters = build_filters_dict(raw_filters)

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

    await state.update_data(
        apartment_filters=filters,
        apartment_offset=len(results),
        apartment_total=total_count,
        apartment_next_offset=next_start,
        apartment_scroll_seen_ids=page_ids,
    )
    await manager.done()

    # Show apartment results respecting view mode
    msg = callback.message
    if not msg:
        return

    if not results:
        await msg.answer("По заданным фильтрам ничего не найдено")
        return

    fsm_data = await state.get_data()
    view_mode = fsm_data.get("catalog_view_mode", "cards")

    if view_mode == "list":
        from telegram_bot.dialogs.funnel import format_apartment_list
        from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

        kb = (
            build_catalog_keyboard(shown=len(results), total=total_count)
            if len(results) < total_count
            else None
        )
        text = format_apartment_list(results, shown_start=1, total=total_count)
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        property_bot = manager.middleware_data.get("property_bot")
        if property_bot is not None:
            telegram_id = callback.from_user.id if callback.from_user else 0
            for result in results:
                with contextlib.suppress(Exception):
                    await property_bot._send_property_card(msg, result, telegram_id)

        if len(results) < total_count:
            from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

            kb = build_catalog_keyboard(shown=len(results), total=total_count)
            await msg.answer(
                f"Показано {len(results)} из {total_count}",
                reply_markup=kb,
            )


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
    # Reset all Radio widgets to unchecked
    for radio_id in _FIELD_TO_RADIO_ID.values():
        with contextlib.suppress(Exception):
            radio_widget = manager.find(radio_id)
            await radio_widget.set_checked(None)


# ============================================================
# Dialog definition — Radio widgets with ✓/○ indicators
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
    # City window — Radio with ✓ indicator
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
        getter=get_promotion_data,
        state=FilterSG.promotion,
    ),
    on_start=on_filter_dialog_start,
)
