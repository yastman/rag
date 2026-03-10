"""Catalog browsing router — SDK-based (StateFilter + F.text filters).

Replaces custom _catalog_mode_filter + _handle_catalog_dispatch with
proper aiogram FSM state routing.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.callback_data import FilterPanelCB
from telegram_bot.dialogs.states import CatalogBrowsingSG
from telegram_bot.handlers.filter_panel import handle_filter_panel
from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard, build_client_keyboard


logger = logging.getLogger(__name__)

catalog_router = Router(name="catalog_browsing")


# --- Показать ещё ---


@catalog_router.message(
    StateFilter(CatalogBrowsingSG.browsing),
    F.text.startswith("📥 Показать"),
    flags={"rate_limit": {"rate": 0.3, "key": "catalog_more"}},
)
async def handle_catalog_more(
    message: Message,
    state: FSMContext,
    property_bot: Any = None,
) -> None:
    """Load next page of apartments."""
    data = await state.get_data()
    offset = data.get("apartment_offset", 0)
    total = data.get("apartment_total", 0)

    if offset >= total:
        return

    svc: Any = getattr(property_bot, "_apartments_service", None) if property_bot else None
    if svc is None:
        return

    results, total_count, new_next_start, page_ids = await svc.scroll_with_filters(
        filters=data.get("apartment_filters"),
        limit=10,
        start_from=data.get("apartment_next_offset"),
        exclude_ids=data.get("apartment_scroll_seen_ids") or None,
    )

    new_offset = offset + len(results)
    catalog_kb = build_catalog_keyboard(shown=new_offset, total=total_count)

    view_mode = data.get("catalog_view_mode", "cards")
    if view_mode == "list":
        from telegram_bot.dialogs.funnel import format_apartment_list

        text = format_apartment_list(results, shown_start=offset + 1, total=total_count)
        await message.answer(text, parse_mode="HTML", reply_markup=catalog_kb)
    else:
        telegram_id = message.from_user.id if message.from_user else 0
        for result in results:
            await property_bot._send_property_card(message, result, telegram_id)
        await message.answer(
            f"Показано {new_offset} из {total_count}",
            reply_markup=catalog_kb,
        )

    await state.update_data(
        apartment_offset=new_offset,
        apartment_total=total_count,
        apartment_next_offset=new_next_start,
        apartment_scroll_seen_ids=page_ids,
    )


# --- Фильтры ---


@catalog_router.message(
    StateFilter(CatalogBrowsingSG.browsing),
    F.text == "🔍 Фильтры",
    flags={"rate_limit": {"rate": 0.3, "key": "catalog_filters"}},
)
async def handle_catalog_filters(
    message: Message,
    state: FSMContext,
    property_bot: Any = None,
) -> None:
    """Show inline filter panel (keeps CatalogBrowsingSG.browsing state)."""
    from telegram_bot.keyboards.filter_panel import (
        build_filter_panel_keyboard,
        build_filter_panel_text,
    )

    data = await state.get_data()
    filters: dict = data.get("apartment_filters") or {}
    svc: Any = getattr(property_bot, "_apartments_service", None) if property_bot else None
    count = data.get("apartment_total", 0)
    if svc is not None:
        with contextlib.suppress(Exception):
            count = await svc.count_with_filters(filters=filters)

    text = build_filter_panel_text(filters=filters, count=count)
    kb = build_filter_panel_keyboard(count=count)
    await message.answer(text, reply_markup=kb)


# --- Избранное ---


@catalog_router.message(
    StateFilter(CatalogBrowsingSG.browsing),
    F.text == "📌 Избранное",
    flags={"rate_limit": {"rate": 0.3, "key": "catalog_bookmarks"}},
)
async def handle_catalog_bookmarks(
    message: Message,
    state: FSMContext,
    property_bot: Any = None,
) -> None:
    """Route to bookmarks handler."""
    if property_bot is not None:
        await property_bot._handle_bookmarks(message, state)


# --- Главное меню ---


@catalog_router.message(
    StateFilter(CatalogBrowsingSG.browsing),
    F.text == "🏠 Главное меню",
    flags={"rate_limit": {"rate": 0.6, "key": "catalog_exit"}},
)
async def handle_catalog_exit(message: Message, state: FSMContext) -> None:
    """Exit catalog mode and restore main keyboard."""
    await state.set_state(None)
    await state.update_data(
        apartment_offset=None,
        apartment_total=None,
        apartment_next_offset=None,
        apartment_scroll_seen_ids=None,
        apartment_filters=None,
    )
    await message.answer("Вы вернулись в главное меню 🏠", reply_markup=build_client_keyboard())


# --- Filter panel inline callbacks ---


@catalog_router.callback_query(
    FilterPanelCB.filter(),
    flags={"rate_limit": {"rate": 0.3, "key": "filter_panel"}},
)
async def handle_filter_panel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: FilterPanelCB,
    apartments_service: Any = None,
) -> None:
    """Dispatch filter panel inline button callbacks."""
    await handle_filter_panel(callback, state, callback_data, apartments_service)


# --- Catch-all: any other text in catalog mode ---


@catalog_router.message(StateFilter(CatalogBrowsingSG.browsing), F.text)
async def handle_catalog_fallback(message: Message) -> None:
    """Ignore unknown text in catalog mode — don't leak to RAG."""
