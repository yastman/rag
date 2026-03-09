"""Inline filter panel callback handlers for apartment catalog.

Handles FilterPanelCB callbacks (prefix="fpanel"):
- action="select": show sub-menu for a filter field
- action="set":    update filter value in FSMContext, return to main panel
- action="apply":  close panel, reset offset (triggers re-search on next scroll)
- action="reset":  clear all filters, show updated panel
- action="back":   back to main panel (from sub-menu) or close panel

Registration: include create_filter_panel_router() in your Dispatcher / Bot setup.
Note: bot.py registration is handled by Group A in the final merge.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.callback_data import FilterPanelCB
from telegram_bot.keyboards.filter_panel import (
    build_filter_options_keyboard,
    build_filter_panel_keyboard,
    build_filter_panel_text,
)


logger = logging.getLogger(__name__)

# Fields that store integer values
_INT_FIELDS = {"rooms", "floor"}


def create_filter_panel_router() -> Router:
    """Create and configure the filter panel router."""
    router = Router(name="filter_panel")

    router.callback_query.register(
        on_filter_panel_select,
        FilterPanelCB.filter(lambda cb: cb.action == "select"),
    )
    router.callback_query.register(
        on_filter_panel_set,
        FilterPanelCB.filter(lambda cb: cb.action == "set"),
    )
    router.callback_query.register(
        on_filter_panel_apply,
        FilterPanelCB.filter(lambda cb: cb.action == "apply"),
    )
    router.callback_query.register(
        on_filter_panel_reset,
        FilterPanelCB.filter(lambda cb: cb.action == "reset"),
    )
    router.callback_query.register(
        on_filter_panel_back,
        FilterPanelCB.filter(lambda cb: cb.action == "back"),
    )

    return router


async def on_filter_panel_select(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
) -> None:
    """Show sub-menu keyboard for a specific filter field."""
    data = await state.get_data()
    filters: dict = data.get("apartment_filters") or {}
    field = callback_data.field

    current_value = filters.get(field)
    try:
        kb = build_filter_options_keyboard(field, current_value=current_value)
        await callback.message.edit_text(  # type: ignore[union-attr]
            text=f"Выберите значение для фильтра «{field}»:",
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Failed to build sub-menu for field %r", field)

    await callback.answer()


async def on_filter_panel_set(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
) -> None:
    """Update a filter value in FSMContext and return to main panel."""
    data = await state.get_data()
    filters: dict = dict(data.get("apartment_filters") or {})
    field = callback_data.field
    value = callback_data.value

    if value == "":
        # Clear this filter
        filters.pop(field, None)
    elif field in _INT_FIELDS:
        try:
            filters[field] = int(value)
        except ValueError:
            filters[field] = value
    else:
        filters[field] = value

    await state.update_data(apartment_filters=filters)

    # Refresh panel with updated filters (count=0 until apply triggers re-search)
    count = data.get("apartment_total", 0)
    panel_text = build_filter_panel_text(filters=filters, count=count)
    panel_kb = build_filter_panel_keyboard(count=count)

    await callback.message.edit_text(  # type: ignore[union-attr]
        text=panel_text,
        reply_markup=panel_kb,
    )
    await callback.answer()


async def on_filter_panel_apply(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
) -> None:
    """Close panel and reset scroll offset so next catalog action re-searches."""
    await state.update_data(apartment_offset=0)
    await callback.message.delete()  # type: ignore[union-attr]
    await callback.answer("Фильтры применены")


async def on_filter_panel_reset(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
) -> None:
    """Clear all filters and show updated (empty) panel."""
    await state.update_data(apartment_filters={})

    data = await state.get_data()
    count = data.get("apartment_total", 0)
    panel_text = build_filter_panel_text(filters={}, count=count)
    panel_kb = build_filter_panel_keyboard(count=count)

    await callback.message.edit_text(  # type: ignore[union-attr]
        text=panel_text,
        reply_markup=panel_kb,
    )
    await callback.answer()


async def on_filter_panel_back(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
) -> None:
    """Handle back action.

    If field is non-empty, we're in a sub-menu — return to main panel.
    If field is empty, we're on the main panel — close it.
    """
    if callback_data.field:
        # Back from sub-menu → show main panel
        data = await state.get_data()
        filters: dict = data.get("apartment_filters") or {}
        count = data.get("apartment_total", 0)
        panel_text = build_filter_panel_text(filters=filters, count=count)
        panel_kb = build_filter_panel_keyboard(count=count)

        await callback.message.edit_text(  # type: ignore[union-attr]
            text=panel_text,
            reply_markup=panel_kb,
        )
    else:
        # Back from main panel → close
        await callback.message.delete()  # type: ignore[union-attr]

    await callback.answer()
