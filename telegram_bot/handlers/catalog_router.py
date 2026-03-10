"""Catalog browsing router — SDK-based (StateFilter + F.text filters).

Replaces custom _catalog_mode_filter + _handle_catalog_dispatch with
proper aiogram FSM state routing.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from telegram_bot.dialogs.states import CatalogBrowsingSG, FilterSG
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
        await message.answer("\u200b", reply_markup=catalog_kb)

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
    dialog_manager: DialogManager,
    property_bot: Any = None,
) -> None:
    """Launch aiogram-dialog FilterDialog for filter editing."""
    data = await state.get_data()
    filters: dict = data.get("apartment_filters") or {}
    # Pass current filters as start_data so dialog can pre-populate dialog_data
    await dialog_manager.start(
        FilterSG.hub,
        data={"filters": filters},
        mode=StartMode.NORMAL,
    )


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


# --- Запись на осмотр ---


@catalog_router.message(
    StateFilter(CatalogBrowsingSG.browsing),
    F.text == "📅 Запись на осмотр",
)
async def handle_catalog_viewing(
    message: Message,
    state: FSMContext,
    property_bot: Any = None,
    dialog_manager: Any = None,
) -> None:
    """Route to viewing appointment from catalog mode."""
    if property_bot is not None:
        await property_bot._handle_viewing(message, state, dialog_manager)


# --- Написать менеджеру ---


@catalog_router.message(
    StateFilter(CatalogBrowsingSG.browsing),
    F.text == "👤 Написать менеджеру",
)
async def handle_catalog_manager(
    message: Message,
    state: FSMContext,
    property_bot: Any = None,
    dialog_manager: Any = None,
) -> None:
    """Route to manager contact from catalog mode."""
    if property_bot is not None:
        await property_bot._handle_manager(message, state=state, dialog_manager=dialog_manager)


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


# --- Catch-all: any other text in catalog mode ---


@catalog_router.message(StateFilter(CatalogBrowsingSG.browsing), F.text)
async def handle_catalog_fallback(message: Message) -> None:
    """Ignore unknown text in catalog mode — don't leak to RAG."""
