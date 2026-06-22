"""Getter functions for all filter dialog windows."""

from __future__ import annotations

import contextlib
from typing import Any

from aiogram_dialog import DialogManager

from telegram_bot.dialogs.filter._state import (
    _ANY_OPTION,
    _main_menu_label_for,
    _sanitize_filter_dialog_state,
)
from telegram_bot.dialogs.filter_constants import (
    AREA_OPTIONS,
    BUDGET_OPTIONS,
    CITY_OPTIONS,
    FIELD_TO_FILTER_KEY,
    FLOOR_OPTIONS,
    ROOMS_OPTIONS,
    VIEW_OPTIONS,
    build_active_filters_summary,
    build_filters_dict,
)


async def get_hub_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter for the hub window — returns filter options and live count."""
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

    active_filters = build_active_filters_summary(dd)
    return {
        "count": count,
        "active_filters": active_filters,
        "btn_main_menu": _main_menu_label_for(dialog_manager),
    }


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
