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
import inspect
import logging
from typing import Any, cast

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage
from aiogram_dialog import Dialog, DialogManager, ShowMode, Window
from aiogram_dialog.utils import remove_intent_id
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
from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard
from telegram_bot.observability import get_client, mask_pii, observe
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


def _clear_filter_dialog_state(manager: DialogManager) -> None:
    """Drop all filter selections from dialog_data and Radio widget state."""
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
    with contextlib.suppress(Exception):
        widget_data = manager.current_context().widget_data
        for radio_id in _FIELD_TO_RADIO_ID.values():
            widget_data.pop(radio_id, None)


def _sanitize_filter_dialog_state(manager: DialogManager) -> None:
    """Remove stale invalid values leaked into dialog_data/widget_data."""
    for field in list(FIELD_TO_FILTER_KEY):
        if not _has_filter_value(manager.dialog_data.get(field)):
            manager.dialog_data.pop(field, None)
    with contextlib.suppress(Exception):
        widget_data = manager.current_context().widget_data
        for radio_id in _FIELD_TO_RADIO_ID.values():
            if not _has_filter_value(widget_data.get(radio_id)):
                widget_data.pop(radio_id, None)


def _main_menu_label_for(dialog_manager: DialogManager) -> str:
    """Return main-menu label even when tests provide a minimal dialog_manager stub."""
    middleware = getattr(dialog_manager, "middleware_data", None) or {}
    i18n = middleware.get("i18n") if isinstance(middleware, dict) else None
    return get_main_menu_label(i18n)


def _state_name(manager: DialogManager) -> str | None:
    with contextlib.suppress(Exception):
        current_context = getattr(manager, "current_context", None)
        if current_context is None or inspect.iscoroutinefunction(current_context):
            return None
        ctx = current_context()
        if inspect.isawaitable(ctx):
            return None
        state_name = getattr(getattr(ctx, "state", None), "state", None)
        return state_name if isinstance(state_name, str) else None
    return None


def _context_ids(manager: DialogManager) -> tuple[str | None, str | None]:
    intent_id: str | None = None
    stack_id: str | None = None
    with contextlib.suppress(Exception):
        current_context = getattr(manager, "current_context", None)
        if current_context is None or inspect.iscoroutinefunction(current_context):
            raise TypeError("current_context() is async")
        ctx = current_context()
        if inspect.isawaitable(ctx):
            raise TypeError("current_context() returned awaitable")
        intent_id = getattr(ctx, "id", None)
        stack_id = getattr(ctx, "stack_id", None)
    return intent_id, stack_id


def _callback_intent_id(callback_data: str | None) -> str | None:
    if not callback_data:
        return None
    with contextlib.suppress(Exception):
        intent_id, _ = remove_intent_id(callback_data)
        return intent_id
    return None


def _snapshot_filter_context(manager: DialogManager) -> dict[str, Any]:
    start_data: dict[str, Any] | None = None
    widget_data: dict[str, Any] | None = None
    with contextlib.suppress(Exception):
        current_context = getattr(manager, "current_context", None)
        if current_context is None or inspect.iscoroutinefunction(current_context):
            raise TypeError("current_context() is async")
        ctx = current_context()
        if inspect.isawaitable(ctx):
            raise TypeError("current_context() returned awaitable")
        start_data = ctx.start_data if isinstance(ctx.start_data, dict) else None
        widget_data = dict(ctx.widget_data)
    intent_id, stack_id = _context_ids(manager)
    return cast(
        dict[str, Any],
        mask_pii(
            {
                "intent_id": intent_id,
                "stack_id": stack_id,
                "state": _state_name(manager),
                "dialog_data": dict(getattr(manager, "dialog_data", {}) or {}),
                "widget_data": widget_data or {},
                "start_data": start_data or {},
            }
        ),
    )


def _trace_filter_output(
    manager: DialogManager,
    *,
    action: str,
    **extra: Any,
) -> dict[str, Any]:
    payload = {"action": action, **extra, "context": _snapshot_filter_context(manager)}
    return cast(dict[str, Any], mask_pii(payload))


def _string_filter_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _start_filter_observation(
    *,
    name: str,
    manager: DialogManager,
    action: str,
    **extra: Any,
):
    lf = get_client()
    if lf is None:
        return contextlib.nullcontext(None)

    payload = mask_pii(
        {
            "action": action,
            **extra,
            "context": _snapshot_filter_context(manager),
        }
    )

    start_observation = getattr(lf, "start_as_current_observation", None)
    if callable(start_observation):
        return start_observation(as_type="span", name=name, input=payload)

    start_span = getattr(lf, "start_as_current_span", None)
    if callable(start_span):
        return start_span(name=name, input=payload)

    return contextlib.nullcontext(None)


def _update_filter_observation(
    observation: Any, *, manager: DialogManager, action: str, **extra: Any
):
    if observation is None or not hasattr(observation, "update"):
        return
    with contextlib.suppress(Exception):
        observation.update(output=_trace_filter_output(manager, action=action, **extra))


def _make_switch_trace_handler(action: str, target_state: Any):
    async def handler(
        callback: CallbackQuery,
        button: Any,
        manager: DialogManager,
    ) -> None:
        with _start_filter_observation(
            name="dialog-filter-button",
            manager=manager,
            action=action,
            button_id=getattr(button, "widget_id", None),
            callback_data=getattr(callback, "data", None),
            target_state=getattr(target_state, "state", str(target_state)),
        ) as observation:
            _update_filter_observation(
                observation,
                manager=manager,
                action=action,
                target_state=getattr(target_state, "state", str(target_state)),
            )

    return handler


# ============================================================
# Hub getter
# ============================================================


@observe(name="dialog-filter-hub-data", capture_input=False, capture_output=False, as_type="span")
async def get_hub_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter for the hub window — returns filter options and live count."""
    lf = get_client()
    if lf is not None:
        lf.update_current_span(input={"context": _snapshot_filter_context(dialog_manager)})
    _sanitize_filter_dialog_state(dialog_manager)

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
            rooms_key = _string_filter_value(rooms_val)
            label = ROOMS_DISPLAY.get(int(rooms_key or "0"), str(rooms_key or ""))
        except (ValueError, TypeError):
            label = str(rooms_val)
        lines.append(f"🛏 Комнаты: {label}")

    budget_val = dd.get("budget")
    if _has_filter_value(budget_val):
        budget_key = _string_filter_value(budget_val) or ""
        lines.append(f"💰 Бюджет: {BUDGET_DISPLAY.get(budget_key, budget_key)}")

    view_val = dd.get("view")
    if _has_filter_value(view_val):
        view_key = _string_filter_value(view_val) or ""
        lines.append(f"🌅 Вид: {VIEW_DISPLAY.get(view_key, view_key)}")

    area_val = dd.get("area")
    if _has_filter_value(area_val):
        area_key = _string_filter_value(area_val) or ""
        lines.append(f"📐 Площадь: {AREA_DISPLAY.get(area_key, area_key)}")

    floor_val = dd.get("floor")
    if _has_filter_value(floor_val):
        floor_key = _string_filter_value(floor_val) or ""
        lines.append(f"🏢 Этаж: {FLOOR_DISPLAY.get(floor_key, floor_key)}")

    complex_val = dd.get("complex")
    if _has_filter_value(complex_val):
        lines.append(f"🏘 Комплекс: {complex_val}")

    furnished_val = dd.get("furnished")
    if _has_filter_value(furnished_val):
        furnished_key = _string_filter_value(furnished_val) or ""
        label = {"true": "Да", "false": "Нет"}.get(furnished_key, furnished_key)
        lines.append(f"🛋 Мебель: {label}")

    promotion_val = dd.get("promotion")
    if promotion_val == "true":
        lines.append("🏷 Только акции")

    active_filters = "\n".join(lines) if lines else "Фильтры не заданы"
    if lf is not None:
        lf.update_current_span(
            output=mask_pii(
                {
                    "count": count,
                    "active_filters": active_filters,
                    "context": _snapshot_filter_context(dialog_manager),
                }
            )
        )

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
        with _start_filter_observation(
            name="dialog-filter-radio-select",
            manager=manager,
            action=f"radio-{field}",
            item_id=item_id,
            callback_data=getattr(callback, "data", None),
        ) as observation:
            if item_id == "any":
                # "Любой" selected — clear this filter
                manager.dialog_data.pop(field, None)
                manager.dialog_data.pop(FIELD_TO_FILTER_KEY.get(field, field), None)
            else:
                # Store raw item_id string — coercion happens in build_filters_dict
                manager.dialog_data[field] = item_id
            await manager.switch_to(FilterSG.hub)
            _update_filter_observation(
                observation,
                manager=manager,
                action=f"radio-{field}",
                item_id=item_id,
            )

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


@observe(name="dialog-filter-start", capture_input=False, capture_output=False, as_type="span")
async def on_filter_dialog_start(
    start_data: dict[str, Any] | None,
    manager: DialogManager,
) -> None:
    """Pre-populate dialog_data and Radio checked states from existing filters."""
    lf = get_client()
    if lf is not None:
        lf.update_current_span(
            input=mask_pii(
                {
                    "start_data": start_data or {},
                    "context_before": _snapshot_filter_context(manager),
                }
            )
        )
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
    if lf is not None:
        lf.update_current_span(output={"context_after": _snapshot_filter_context(manager)})


# ============================================================
# on_apply — save filters to FSMContext, done()
# ============================================================


async def on_apply(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Apply filters and return to the catalog dialog flow."""
    with _start_filter_observation(
        name="dialog-filter-apply",
        manager=manager,
        action="apply",
        button_id=getattr(button, "widget_id", None),
        callback_data=getattr(callback, "data", None),
    ) as observation:
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
        if msg is None or isinstance(msg, InaccessibleMessage):
            _update_filter_observation(
                observation, manager=manager, action="apply", has_message=False
            )
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
            _update_filter_observation(
                observation,
                manager=manager,
                action="apply",
                result_state=CatalogSG.empty.state,
                result_count=0,
            )
            return

        await send_catalog_results(
            message=msg,
            property_bot=manager.middleware_data.get("property_bot"),
            results=results,
            total_count=total_count,
            view_mode=runtime.get("view_mode", "cards"),
            shown_start=1,
            telegram_id=callback.from_user.id if callback.from_user else 0,
            reply_markup=(
                build_catalog_keyboard(
                    shown=len(results),
                    total=total_count,
                    i18n=manager.middleware_data.get("i18n"),
                )
                if runtime.get("view_mode", "cards") == "list"
                else None
            ),
        )
        await show_catalog_controls(message=msg, dialog_manager=manager, runtime=runtime)
        await activate_catalog_state(dialog_manager=manager, state=CatalogSG.results)
        _update_filter_observation(
            observation,
            manager=manager,
            action="apply",
            result_state=CatalogSG.results.state,
            result_count=total_count,
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
    with _start_filter_observation(
        name="dialog-filter-reset",
        manager=manager,
        action="reset",
        button_id=getattr(button, "widget_id", None),
        callback_data=getattr(callback, "data", None),
        callback_intent_id=_callback_intent_id(getattr(callback, "data", None)),
    ) as observation:
        _clear_filter_dialog_state(manager)
        state_name = _state_name(manager)
        if state_name == FilterSG.hub.state:
            await manager.update({}, show_mode=ShowMode.EDIT)
        else:
            await manager.switch_to(FilterSG.hub, show_mode=ShowMode.EDIT)
        _update_filter_observation(
            observation,
            manager=manager,
            action="reset",
            result_state=FilterSG.hub.state,
        )


# ============================================================
# Dialog definition — Radio widgets with ✓/○ indicators
# ============================================================

filter_dialog = Dialog(
    # Hub window: filter summary + navigation
    Window(
        Format("🏠 Фильтры поиска\n\n{active_filters}\n\nНайдено: {count} апартаментов"),
        Row(
            SwitchTo(
                Const("📍 Город"),
                id="sw_city",
                state=FilterSG.city,
                on_click=_make_switch_trace_handler("open-city", FilterSG.city),
            ),
            SwitchTo(
                Const("🛏 Комнаты"),
                id="sw_rooms",
                state=FilterSG.rooms,
                on_click=_make_switch_trace_handler("open-rooms", FilterSG.rooms),
            ),
            SwitchTo(
                Const("💰 Бюджет"),
                id="sw_budget",
                state=FilterSG.budget,
                on_click=_make_switch_trace_handler("open-budget", FilterSG.budget),
            ),
        ),
        Row(
            SwitchTo(
                Const("🌅 Вид"),
                id="sw_view",
                state=FilterSG.view,
                on_click=_make_switch_trace_handler("open-view", FilterSG.view),
            ),
            SwitchTo(
                Const("📐 Площадь"),
                id="sw_area",
                state=FilterSG.area,
                on_click=_make_switch_trace_handler("open-area", FilterSG.area),
            ),
            SwitchTo(
                Const("🏢 Этаж"),
                id="sw_floor",
                state=FilterSG.floor,
                on_click=_make_switch_trace_handler("open-floor", FilterSG.floor),
            ),
        ),
        Row(
            SwitchTo(
                Const("🏘 Комплекс"),
                id="sw_complex",
                state=FilterSG.complex_name,
                on_click=_make_switch_trace_handler("open-complex", FilterSG.complex_name),
            ),
            SwitchTo(
                Const("🛋 Мебель"),
                id="sw_furnished",
                state=FilterSG.furnished,
                on_click=_make_switch_trace_handler("open-furnished", FilterSG.furnished),
            ),
            SwitchTo(
                Const("🏷 Акции"),
                id="sw_promotion",
                state=FilterSG.promotion,
                on_click=_make_switch_trace_handler("open-promotion", FilterSG.promotion),
            ),
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
        SwitchTo(
            Const("← Назад"),
            id="back_city",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-city", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_rooms",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-rooms", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_budget",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-budget", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_view",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-view", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_area",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-area", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_floor",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-floor", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_complex",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-complex", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_furnished",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-furnished", FilterSG.hub),
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
        root_menu_button(),
        SwitchTo(
            Const("← Назад"),
            id="back_promotion",
            state=FilterSG.hub,
            on_click=_make_switch_trace_handler("back-promotion", FilterSG.hub),
        ),
        getter=get_promotion_data,
        state=FilterSG.promotion,
    ),
    on_start=on_filter_dialog_start,
)
