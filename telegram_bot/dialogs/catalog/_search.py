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
from telegram_bot.dialogs.states import CatalogSG
from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard
from telegram_bot.services.apartment.catalog_rendering import send_catalog_results
from telegram_bot.services.apartment.catalog_session import (
    CatalogRuntime,
    update_catalog_runtime_page,
)


_PAGE_SIZE = 10


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

    property_bot = dialog_manager.middleware_data.get("property_bot")
    apartments_service = dialog_manager.middleware_data.get("apartments_service")
    if apartments_service is None and property_bot is not None:
        apartments_service = getattr(property_bot, "_apartments_service", None)
    if apartments_service is None:
        return runtime

    (
        results,
        total_count,
        new_next_offset,
        shown_item_ids,
    ) = await apartments_service.scroll_with_filters(
        filters=runtime.get("filters"),
        limit=_PAGE_SIZE,
        start_from=next_offset,
        exclude_ids=runtime.get("shown_item_ids") or None,
    )

    effective_telegram_id = telegram_id if telegram_id is not None else 0
    if not effective_telegram_id and message.from_user:
        effective_telegram_id = message.from_user.id
    i18n = dialog_manager.middleware_data.get("i18n")
    await send_catalog_results(
        message=message,
        property_bot=property_bot,
        results=results,
        total_count=total_count,
        view_mode=runtime.get("view_mode", "cards"),
        shown_start=shown_count + 1,
        telegram_id=effective_telegram_id,
        reply_markup=(
            _catalog_reply_markup(
                {
                    **runtime,
                    "shown_count": shown_count + len(results),
                    "total": total_count,
                },
                i18n=i18n,
            )
            if runtime.get("view_mode", "cards") == "list"
            else None
        ),
    )

    updated = update_catalog_runtime_page(
        runtime,
        results=results,
        total=total_count,
        next_offset=new_next_offset,
        shown_item_ids=shown_item_ids,
    )
    await _update_catalog_runtime(dialog_manager, updated)
    return updated


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
