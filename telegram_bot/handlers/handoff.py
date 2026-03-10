"""Manager handoff: qualification flow + Forum Topics bridge.

Qualification is handled by aiogram-dialog (HandoffSG in dialogs/handoff.py).
This module retains FSM states, callback parsing helpers, and the dialog launcher.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


class HandoffStates(StatesGroup):
    """FSM states for handoff flow."""

    active = State()


logger = logging.getLogger(__name__)

# ── Callback parsing ────────────────────────────────────────────


def parse_qual_callback(data: str) -> tuple[str, str] | None:
    parts = data.split(":")
    if len(parts) == 3 and parts[0] == "qual":
        return parts[1], parts[2]
    return None


# ── Start qualification (aiogram-dialog) ────────────────────────


async def start_qualification(
    message_or_callback: Any,
    i18n: Any | None = None,
    state: FSMContext | None = None,
    dialog_manager: Any | None = None,
    goal: str | None = None,
) -> None:
    """Launch handoff qualification dialog (aiogram-dialog).

    Args:
        goal: Pre-selected goal (e.g. "services") — skips goal selection step.
    """
    # FSM guard: if handoff already active, don't start again.
    if state is not None and await state.get_state() == HandoffStates.active:
        reply = "Вы уже на связи с менеджером, ожидайте ответа 💬"
        if hasattr(message_or_callback, "message"):
            await message_or_callback.answer()
            msg = message_or_callback.message
            if msg and hasattr(msg, "answer"):
                await msg.answer(reply)
        else:
            await message_or_callback.answer(reply)
        return

    if dialog_manager is not None:
        from aiogram_dialog import StartMode

        from telegram_bot.dialogs.states import HandoffSG

        if goal:
            # Context already known — skip goal step, go directly to contact.
            await dialog_manager.start(
                HandoffSG.contact,
                data={"goal": goal},
                mode=StartMode.RESET_STACK,
            )
        else:
            await dialog_manager.start(HandoffSG.goal, mode=StartMode.RESET_STACK)
    else:
        # Fallback when dialog_manager not available — send plain text.
        logger.warning("start_qualification called without dialog_manager")
        text = "📋 Какая тема вас интересует?"
        if hasattr(message_or_callback, "message"):
            await message_or_callback.answer()
            msg = message_or_callback.message
            if msg and hasattr(msg, "answer"):
                await msg.answer(text)
        else:
            await message_or_callback.answer(text)
