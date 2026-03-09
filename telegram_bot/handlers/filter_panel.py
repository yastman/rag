"""Filter panel callback handlers — inline filter panel for apartment catalog.

Registration in bot.py is handled by Group A / final merge.
This module exposes `handle_filter_panel` coroutine for use as a callback handler.
"""

from __future__ import annotations

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


async def handle_filter_panel(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
) -> None:
    """Dispatch filter panel callback by action."""
    action = callback_data.action
    field = callback_data.field
    value = callback_data.value

    try:
        if action == "select":
            await _handle_select(callback, state, field)
        elif action == "set":
            await _handle_set(callback, state, field, value)
        elif action == "apply":
            await _handle_apply(callback, state)
        elif action == "reset":
            await _handle_reset(callback, state)
        elif action == "back":
            await _handle_back(callback)
        elif action == "main":
            await _handle_main(callback, state)
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
    current_value = filters.get(field)

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

    # Refresh panel with updated filters
    total = data.get("apartment_total", 0)
    text = build_filter_panel_text(filters=filters, count=total)
    kb = build_filter_panel_keyboard(count=total)
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
) -> None:
    """Clear all filters and refresh panel."""
    data = await state.get_data()
    total = data.get("apartment_total", 0)

    await state.update_data(apartment_filters={})

    text = build_filter_panel_text(filters={}, count=total)
    kb = build_filter_panel_keyboard(count=total)
    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer("Фильтры сброшены")


async def _handle_back(callback: CallbackQuery) -> None:
    """Delete filter panel message and return to catalog."""
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer()


async def _handle_main(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Return to main filter panel screen from sub-menu."""
    data = await state.get_data()
    filters: dict[str, Any] = data.get("apartment_filters") or {}
    total = data.get("apartment_total", 0)

    text = build_filter_panel_text(filters=filters, count=total)
    kb = build_filter_panel_keyboard(count=total)
    await callback.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    await callback.answer()


def _field_to_filter_key(field: str) -> str:
    """Map panel field name to apartment_filters dict key."""
    _MAP = {
        "city": "city",
        "rooms": "rooms",
        "budget": "budget",
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
    if field == "rooms":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if field == "furnished":
        return value == "true"
    if field == "promotion":
        return value == "true"
    return value or None
