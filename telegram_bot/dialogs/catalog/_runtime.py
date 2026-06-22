"""Catalog FSM-state runtime helpers — no cross-dialog imports."""

from __future__ import annotations

import contextlib
from typing import Any, cast

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from aiogram_dialog import DialogManager

from telegram_bot.services.catalog_session import (
    CATALOG_RUNTIME_DATA_KEY,
    CatalogRuntime,
)


def _empty_catalog_runtime() -> CatalogRuntime:
    return cast(CatalogRuntime, {})


def _copy_catalog_runtime(runtime: CatalogRuntime) -> CatalogRuntime:
    return cast(CatalogRuntime, dict(runtime))


def _runtime_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            return int(value)
    return 0


def _callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if message is None or isinstance(message, InaccessibleMessage):
        return None
    return message


async def _get_state(dialog_manager: DialogManager) -> FSMContext | None:
    state = dialog_manager.middleware_data.get("state")
    if isinstance(state, FSMContext):
        return state
    return state


async def _get_catalog_runtime(dialog_manager: DialogManager) -> CatalogRuntime:
    state = await _get_state(dialog_manager)
    if state is None:
        return _empty_catalog_runtime()
    data = await state.get_data()
    runtime = data.get(CATALOG_RUNTIME_DATA_KEY)
    if isinstance(runtime, dict):
        return cast(CatalogRuntime, runtime)
    return _empty_catalog_runtime()


async def _update_catalog_runtime(dialog_manager: DialogManager, runtime: CatalogRuntime) -> None:
    state = await _get_state(dialog_manager)
    if state is None:
        return
    await state.update_data(**{CATALOG_RUNTIME_DATA_KEY: runtime})


def is_catalog_state(state_name: str | None) -> bool:
    return isinstance(state_name, str) and state_name.startswith("CatalogSG:")


__all__ = [
    "_callback_message",
    "_copy_catalog_runtime",
    "_empty_catalog_runtime",
    "_get_catalog_runtime",
    "_get_state",
    "_runtime_int",
    "_update_catalog_runtime",
    "is_catalog_state",
]


def _catalog_reply_markup(runtime: CatalogRuntime, *, i18n: Any = None) -> Any:
    from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard

    return build_catalog_keyboard(
        shown=_runtime_int(runtime.get("shown_count")),
        total=_runtime_int(runtime.get("total")),
        i18n=i18n,
    )
