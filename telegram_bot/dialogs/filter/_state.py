"""Shared helpers, constants, and observation stubs for filter_dialog."""

from __future__ import annotations

import contextlib
import inspect
from typing import Any, cast

from aiogram_dialog import DialogManager
from aiogram_dialog.utils import remove_intent_id

from telegram_bot.dialogs.filter_constants import FIELD_TO_FILTER_KEY
from telegram_bot.dialogs.root_nav import get_main_menu_label
from telegram_bot.observability import mask_pii


# "Любой" option used in every filter sub-menu to clear that filter.
# IMPORTANT: use "any" (not "") — aiogram-dialog widgets skip empty item_ids.
_ANY_OPTION = ("Любой", "any")

# Map dialog_data field → radio_widget_id
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
        return intent_id if isinstance(intent_id, str) else None
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


def _start_filter_observation(
    *,
    name: str,
    manager: DialogManager,
    action: str,
    **extra: Any,
):
    """No-op stub — tracing removed (#2844)."""
    return contextlib.nullcontext(None)


def _update_filter_observation(
    observation: Any, *, manager: DialogManager, action: str, **extra: Any
):
    """No-op stub — tracing removed (#2844)."""


def _make_switch_trace_handler(action: str, target_state: Any):
    from aiogram.types import CallbackQuery

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
