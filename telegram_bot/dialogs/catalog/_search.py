"""Catalog search/pagination actions and post-search render sequence."""

from __future__ import annotations

import inspect
from typing import Any

from aiogram.types import Message
from aiogram_dialog import DialogManager, ShowMode, StartMode

from telegram_bot.dialogs.catalog._controls import show_catalog_controls
from telegram_bot.dialogs.catalog._runtime import (
    _catalog_reply_markup,
    _get_catalog_runtime,
    _update_catalog_runtime,
)
from telegram_bot.dialogs.states import CatalogSG, DemoSG
from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard
from telegram_bot.services.apartment.apartment_catalog import ApartmentCatalog
from telegram_bot.services.apartment.catalog_rendering import send_catalog_results
from telegram_bot.services.apartment.catalog_session import (
    CATALOG_RUNTIME_DATA_KEY,
    CatalogRuntime,
    build_catalog_runtime,
    update_catalog_runtime_page,
)
from telegram_bot.services.favorites_service import bookmarks_ready


async def activate_catalog_state(
    *,
    dialog_manager: DialogManager,
    state: Any,
) -> None:
    maybe_start = dialog_manager.start(
        state,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.NO_UPDATE,
    )
    if inspect.isawaitable(maybe_start):
        await maybe_start


async def load_next_catalog_page(
    *,
    message: Message,
    dialog_manager: DialogManager,
    telegram_id: int | None = None,
) -> CatalogRuntime:
    runtime = await _get_catalog_runtime(dialog_manager)
    shown_count = int(runtime.get("shown_count", 0) or 0)
    total = int(runtime.get("total", 0) or 0)
    next_offset = runtime.get("next_offset")

    if shown_count >= total or next_offset is None:
        return runtime

    catalog = ApartmentCatalog.from_dialog_manager(dialog_manager)
    if not catalog.service_available:
        return runtime

    page = await catalog.continue_page(
        query=str(runtime.get("query") or ""),
        filters=runtime.get("filters"),
        next_offset=next_offset,
        shown_item_ids=runtime.get("shown_item_ids") or [],
    )

    effective_telegram_id = telegram_id if telegram_id is not None else 0
    if not effective_telegram_id and message.from_user:
        effective_telegram_id = message.from_user.id
    i18n = dialog_manager.middleware_data.get("i18n")
    view_mode = runtime.get("view_mode", "cards")
    await send_catalog_results(
        message=message,
        property_bot=dialog_manager.middleware_data.get("property_bot"),
        results=page.results,
        total_count=page.total,
        view_mode=view_mode,
        shown_start=shown_count + 1,
        telegram_id=effective_telegram_id,
        reply_markup=(
            _catalog_reply_markup(
                {
                    **runtime,
                    "shown_count": shown_count + len(page.results),
                    "total": page.total,
                },
                i18n=i18n,
                bookmarks_available=bookmarks_ready(
                    dialog_manager.middleware_data.get("property_bot")
                ),
            )
            if view_mode == "list"
            else None
        ),
    )

    updated = update_catalog_runtime_page(
        runtime,
        results=page.results,
        total=page.total,
        next_offset=page.next_offset,
        shown_item_ids=page.shown_item_ids,
    )
    await _update_catalog_runtime(dialog_manager, updated)
    return updated


async def search_catalog_from_query(
    *,
    message: Message,
    dialog_manager: DialogManager,
    query: str,
    source: str = "demo",
    view_mode: str = "list",
) -> None:
    """Shared demo/catalog free-text search entrypoint (#3238).

    Runs one :class:`ApartmentCatalog` search for ``query`` — regex-first
    extraction with optional structured gap-fill, Qdrant payload filtering
    with price order, cursor-ready first page — then persists the catalog
    runtime and renders results/navigation identically for both entrypoints.

    The degraded no-service branch keeps the legacy demo-window behavior
    (extraction echo + "search unavailable" note) so bot-only deployments
    still work.
    """
    catalog = ApartmentCatalog.from_dialog_manager(dialog_manager)
    if not catalog.extraction_available:
        await message.answer("Сервис поиска временно недоступен.")
        return

    await message.answer("🔍 Ищу подходящие варианты...")
    extraction = await catalog.extract(query)
    if extraction is None:
        # No extraction pipeline wired: degrade to the degraded-mode branch,
        # which reports the (absent) filters instead of searching.
        await message.answer("Сервис поиска временно недоступен.")
        return

    if not catalog.service_available:
        dialog_manager.dialog_data["results"] = []
        dialog_manager.dialog_data["count"] = 0
        dialog_manager.dialog_data["query"] = query
        dialog_manager.dialog_data["degraded_text"] = (
            f"📋 Распознано: {extraction.hard.model_dump(exclude_none=True)}\n"
            "(поиск недоступен в тестовом режиме)"
        )
        await dialog_manager.switch_to(DemoSG.results)
        return

    page = await catalog.search(query, filters=extraction.hard.to_filters_dict() or None)
    runtime = build_catalog_runtime(
        query=query,
        source=source,
        filters=page.filters,
        view_mode=view_mode,
        results=page.results,
        total=page.total,
        next_offset=page.next_offset,
        shown_item_ids=page.shown_item_ids,
    )
    state = dialog_manager.middleware_data.get("state")
    if state is not None:
        await state.update_data(**{CATALOG_RUNTIME_DATA_KEY: runtime})

    if page.is_empty:
        await show_catalog_controls(message=message, dialog_manager=dialog_manager, runtime=runtime)
        await activate_catalog_state(dialog_manager=dialog_manager, state=CatalogSG.empty)
        return

    await send_catalog_results(
        message=message,
        property_bot=dialog_manager.middleware_data.get("property_bot"),
        results=page.results,
        total_count=page.total,
        view_mode=view_mode,
        shown_start=1,
        telegram_id=message.from_user.id if message.from_user else 0,
        reply_markup=build_catalog_keyboard(
            shown=len(page.results),
            total=page.total,
            i18n=dialog_manager.middleware_data.get("i18n"),
            bookmarks_available=bookmarks_ready(
                dialog_manager.middleware_data.get("property_bot")
            ),
        ),
    )
    await show_catalog_controls(message=message, dialog_manager=dialog_manager, runtime=runtime)
    await activate_catalog_state(dialog_manager=dialog_manager, state=CatalogSG.results)


__all__ = [
    "activate_catalog_state",
    "load_next_catalog_page",
    "run_catalog_search_and_render",
    "search_catalog_from_query",
]


async def run_catalog_search_and_render(
    *,
    msg: Message,
    manager: DialogManager,
    runtime: CatalogRuntime,
    results: list[Any],
    property_bot: Any,
    view_mode: str,
    telegram_id: int,
) -> None:
    """Close dialog shell, delete its message, then render search results.

    Shared post-search render sequence used by FunnelSG and FilterSG to
    avoid duplicating the close → delete → show pattern (#2948 Step 5).

    Callers are responsible for building ``runtime`` and running the search;
    this helper owns everything that happens afterwards.
    """
    manager.show_mode = ShowMode.NO_UPDATE
    await manager.done()
    if hasattr(msg, "delete"):
        import contextlib

        with contextlib.suppress(Exception):
            await msg.delete()

    if not results:
        await show_catalog_controls(message=msg, dialog_manager=manager, runtime=runtime)
        await activate_catalog_state(dialog_manager=manager, state=CatalogSG.empty)
        return

    i18n = manager.middleware_data.get("i18n")
    await send_catalog_results(
        message=msg,
        property_bot=property_bot,
        results=results,
        total_count=int(runtime.get("total", len(results)) or len(results)),
        view_mode=view_mode,
        shown_start=1,
        telegram_id=telegram_id,
        reply_markup=(
            build_catalog_keyboard(
                shown=len(results),
                total=int(runtime.get("total", len(results)) or len(results)),
                i18n=i18n,
                bookmarks_available=bookmarks_ready(
                    manager.middleware_data.get("property_bot")
                ),
            )
            if view_mode == "list"
            else None
        ),
    )
    await show_catalog_controls(message=msg, dialog_manager=manager, runtime=runtime)
    await activate_catalog_state(dialog_manager=manager, state=CatalogSG.results)


__all__ = [
    "activate_catalog_state",
    "load_next_catalog_page",
    "run_catalog_search_and_render",
]
