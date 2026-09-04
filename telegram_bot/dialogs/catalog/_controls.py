"""Catalog control-message helpers (send/clear the persistent reply-keyboard message)."""

from __future__ import annotations

import contextlib

from aiogram.types import Message
from aiogram_dialog import DialogManager

from telegram_bot.capabilities import bookmarks_ready
from telegram_bot.dialogs.catalog._runtime import (
    _catalog_reply_markup,
    _copy_catalog_runtime,
    _get_catalog_runtime,
    _runtime_int,
    _update_catalog_runtime,
)
from telegram_bot.services.apartment.catalog_session import CatalogRuntime


def _control_text(runtime: CatalogRuntime) -> str:
    total = _runtime_int(runtime.get("total"))
    shown = _runtime_int(runtime.get("shown_count"))
    query = runtime.get("query") or ""
    source = runtime.get("source") or "catalog"
    view_mode = runtime.get("view_mode") or "cards"

    if total <= 0:
        return "Каталог пуст. Измените фильтры или отправьте новый запрос."

    lines = [f"Показано {shown} из {total}"]
    if query:
        lines.append(f"Запрос: {query}")
    lines.append(f"Источник: {source}")
    lines.append(f"Режим: {view_mode}")
    return "\n".join(lines)


async def clear_catalog_controls(
    *,
    message: Message,
    dialog_manager: DialogManager,
) -> CatalogRuntime:
    runtime = _copy_catalog_runtime(await _get_catalog_runtime(dialog_manager))
    control_message_id = runtime.pop("control_message_id", None)
    if control_message_id and message.bot is not None:
        with contextlib.suppress(Exception):
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=int(control_message_id),
            )
    await _update_catalog_runtime(dialog_manager, runtime)
    return runtime


async def show_catalog_controls(
    *,
    message: Message,
    dialog_manager: DialogManager,
    runtime: CatalogRuntime | None = None,
    text: str | None = None,
) -> CatalogRuntime:
    source_runtime = runtime if runtime is not None else await _get_catalog_runtime(dialog_manager)
    current_runtime = _copy_catalog_runtime(source_runtime)
    control_message_id = current_runtime.pop("control_message_id", None)
    if control_message_id and message.bot is not None:
        with contextlib.suppress(Exception):
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=int(control_message_id),
            )
    i18n = dialog_manager.middleware_data.get("i18n")
    bookmarks_available = bookmarks_ready(dialog_manager.middleware_data.get("property_bot"))
    if (
        text is None
        and current_runtime.get("view_mode") == "list"
        and int(current_runtime.get("total", 0) or 0) > 0
    ):
        await _update_catalog_runtime(dialog_manager, current_runtime)
        return current_runtime
    sent = await message.answer(
        text or _control_text(current_runtime),
        reply_markup=_catalog_reply_markup(
            current_runtime, i18n=i18n, bookmarks_available=bookmarks_available
        ),
    )
    message_id = getattr(sent, "message_id", None)
    if isinstance(message_id, int):
        current_runtime["control_message_id"] = message_id
    await _update_catalog_runtime(dialog_manager, current_runtime)
    return current_runtime


__all__ = [
    "clear_catalog_controls",
    "show_catalog_controls",
]
