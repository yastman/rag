"""Filter panel callback handlers — inline filter panel for apartment catalog.

Registration in bot.py is handled by Group A / final merge.
This module exposes `handle_filter_panel` coroutine for use as a callback handler.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.callback_data import FilterPanelCB
from telegram_bot.keyboards.filter_panel import (
    build_filter_options_keyboard,
    build_filter_panel_keyboard,
    build_filter_panel_text,
)


logger = logging.getLogger(__name__)

_BUDGET_TO_PRICE: dict[str, dict[str, int]] = {
    "low": {"lte": 50_000},
    "mid": {"gte": 50_000, "lte": 100_000},
    "high": {"gte": 100_000, "lte": 150_000},
    "premium": {"gte": 150_000, "lte": 200_000},
    "luxury": {"gte": 200_000},
}

_PRICE_TO_BUDGET: dict[str, str] = {str(v): k for k, v in _BUDGET_TO_PRICE.items()}


def _price_to_budget(price_filter: dict) -> str | None:
    """Reverse-map price_eur filter dict to budget label."""
    return _PRICE_TO_BUDGET.get(str(price_filter))


async def handle_filter_panel(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
    apartments_service: Any = None,
) -> None:
    """Dispatch filter panel callback by action."""
    action = callback_data.action
    field = callback_data.field
    value = callback_data.value

    try:
        if action == "select":
            await _handle_select(callback, state, field)
        elif action == "set":
            await _handle_set(callback, state, field, value, apartments_service)
        elif action == "apply":
            await _handle_apply(callback, state)
        elif action == "reset":
            await _handle_reset(callback, state, apartments_service)
        elif action == "back":
            await _handle_back(callback)
        elif action == "main":
            await _handle_main(callback, state, apartments_service)
        else:
            logger.warning("Unknown filter panel action: %s", action)
            await callback.answer()
    except Exception:
        logger.exception("Error in filter panel handler, action=%s field=%s", action, field)
        await callback.answer("Произошла ошибка", show_alert=True)


async def _handle_select(
    callback: CallbackQuery,
    state: FSMContext,
    field: str,
) -> None:
    """Show sub-menu for a specific filter field."""
    data = await state.get_data()
    filters: dict[str, Any] = data.get("apartment_filters") or {}
    filter_key = _field_to_filter_key(field)
    current_value = filters.get(filter_key)
    # For budget, reverse-map price_eur dict back to budget label
    if field == "budget" and isinstance(current_value, dict):
        current_value = _price_to_budget(current_value)

    kb = build_filter_options_keyboard(field, current_value=current_value)

    # Build sub-menu header text
    _FIELD_LABELS = {
        "city": "📍 Выберите город",
        "rooms": "🛏 Выберите количество комнат",
        "budget": "💰 Выберите бюджет",
        "view": "🌅 Выберите вид",
        "area": "📐 Выберите площадь",
        "floor": "🏢 Выберите этаж",
        "complex": "🏘 Выберите комплекс",
        "furnished": "🛋 Мебель",
        "promotion": "🏷 Акции",
    }
    header = _FIELD_LABELS.get(field, f"Выберите {field}")
    text = f"{header}\n\nТекущее значение: {current_value or 'не задано'}"

    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer()


async def _handle_set(
    callback: CallbackQuery,
    state: FSMContext,
    field: str,
    value: str,
    apartments_service: Any = None,
) -> None:
    """Set a filter value and return to main panel."""
    data = await state.get_data()
    filters: dict[str, Any] = dict(data.get("apartment_filters") or {})

    if value == "":
        # Clear this specific filter
        filters.pop(field, None)
        filters.pop(_field_to_filter_key(field), None)
    else:
        # Map field name to filter key and coerce value
        filter_key = _field_to_filter_key(field)
        coerced = _coerce_value(field, value)
        if coerced is None:
            filters.pop(filter_key, None)
        else:
            filters[filter_key] = coerced

    await state.update_data(apartment_filters=filters)

    count = await _get_count(filters, data, apartments_service)
    text = build_filter_panel_text(filters=filters, count=count)
    kb = build_filter_panel_keyboard(count=count)
    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer()


async def _handle_apply(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Apply current filters — reset offset to start fresh search."""
    await state.update_data(apartment_offset=0)
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer("Фильтры применены")


async def _handle_reset(
    callback: CallbackQuery,
    state: FSMContext,
    apartments_service: Any = None,
) -> None:
    """Clear all filters and refresh panel."""
    data = await state.get_data()
    await state.update_data(apartment_filters={})

    count = await _get_count({}, data, apartments_service)
    text = build_filter_panel_text(filters={}, count=count)
    kb = build_filter_panel_keyboard(count=count)
    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer("Фильтры сброшены")


async def _handle_back(callback: CallbackQuery) -> None:
    """Delete filter panel message and return to catalog."""
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer()


async def _handle_main(
    callback: CallbackQuery,
    state: FSMContext,
    apartments_service: Any = None,
) -> None:
    """Return to main filter panel screen from sub-menu."""
    data = await state.get_data()
    filters: dict[str, Any] = data.get("apartment_filters") or {}

    count = await _get_count(filters, data, apartments_service)
    text = build_filter_panel_text(filters=filters, count=count)
    kb = build_filter_panel_keyboard(count=count)
    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer()


async def _get_count(
    filters: dict[str, Any],
    state_data: dict[str, Any],
    apartments_service: Any,
) -> int:
    """Get live apartment count for filters, falling back to stale total."""
    if apartments_service is not None:
        with contextlib.suppress(Exception):
            return await apartments_service.count_with_filters(filters=filters)
    return state_data.get("apartment_total", 0)


def _field_to_filter_key(field: str) -> str:
    """Map panel field name to apartment_filters dict key."""
    _MAP = {
        "city": "city",
        "rooms": "rooms",
        "budget": "price_eur",
        "view": "view_tags",
        "area": "area_m2",
        "floor": "floor",
        "complex": "complex_name",
        "furnished": "is_furnished",
        "promotion": "is_promotion",
    }
    return _MAP.get(field, field)


def _coerce_value(field: str, value: str) -> Any:
    """Coerce string value to appropriate Python type for filter."""
    if field in ("rooms", "floor"):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if field == "area":
        try:
            return {"gte": int(value)}
        except (ValueError, TypeError):
            return None
    if field == "budget":
        return _BUDGET_TO_PRICE.get(value)
    if field in ("furnished", "promotion"):
        return value == "true"
    if field == "view":
        return [value] if value else None
    return value or None
