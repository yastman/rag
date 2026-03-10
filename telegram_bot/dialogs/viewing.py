"""Viewing appointment wizard dialog (aiogram-dialog).

Flow: date selection → phone_collector FSM (same as handoff).
"""

from __future__ import annotations

import contextlib
import logging
import operator
import time
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, ShowMode, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, Column, Select
from aiogram_dialog.widgets.text import Format

from .states import HandoffSG, ViewingSG


logger = logging.getLogger(__name__)


# --- Date range → label mapping ---

DATE_LABELS: dict[str, str] = {
    "nearest": "📅 Ближайшие дни",
    "next_week": "📅 Через неделю",
    "next_month": "📅 Через месяц",
    "unknown": "🤷 Не знаю когда",
    "phone": "📞 Согласуем по телефону",
}

# --- Due date offsets (seconds) ---

_DUE_OFFSETS: dict[str, int] = {
    "nearest": 3 * 86400,
    "next_week": 7 * 86400,
    "next_month": 30 * 86400,
    "unknown": 7 * 86400,
    "phone": 1 * 86400,
}


def compute_due_date(date_range: str) -> int:
    """Compute unix timestamp for CRM task due date."""
    return int(time.time()) + _DUE_OFFSETS.get(date_range, 7 * 86400)


# ── Getter ───────────────────────────────────────────────────────────


async def get_date_options(
    dialog_manager: DialogManager | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Getter for date range selection."""
    items = list(DATE_LABELS.items())  # [(key, label), ...]
    return {
        "title": "📅 Когда удобно осмотреть?",
        "items": [(label, key) for key, label in items],
        "btn_cancel": "✉ Написать менеджеру",
    }


# ── Handlers ─────────────────────────────────────────────────────────


async def on_cancel_to_manager(
    callback: CallbackQuery, button: Button, manager: DialogManager
) -> None:
    """Cancel viewing and redirect to manager handoff."""
    await manager.start(HandoffSG.goal, mode=StartMode.RESET_STACK)


async def on_date_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save date range, close dialog, start phone_collector FSM."""
    # Grab FSM state BEFORE done() destroys dialog context.
    state = manager.middleware_data.get("state")

    manager.show_mode = ShowMode.NO_UPDATE
    await manager.done()

    # Remove inline keyboard message — phone_collector sends its own prompt.
    msg = callback.message
    if msg and hasattr(msg, "delete"):
        with contextlib.suppress(Exception):
            await msg.delete()

    if state is None:
        logger.warning("FSMContext not in middleware_data for viewing phone handoff")
        return

    # Store date_range in FSM state so phone_collector includes it in CRM note.
    await state.update_data(date_range=item_id)

    from telegram_bot.handlers.phone_collector import start_phone_collection

    await start_phone_collection(callback, state, service_key="viewing")


# ── Dialog Assembly ──────────────────────────────────────────────────

viewing_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="viewing_date",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_date_selected,
            ),
        ),
        Button(Format("{btn_cancel}"), id="cancel", on_click=on_cancel_to_manager),
        getter=get_date_options,
        state=ViewingSG.date,
    ),
)
