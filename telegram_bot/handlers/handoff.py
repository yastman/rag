"""Manager handoff: qualification flow + Forum Topics bridge.

Callback data format: qual:{step}:{value}
Steps: goal → budget → contact
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup


logger = logging.getLogger(__name__)

# ── Callback parsing ────────────────────────────────────────────


def parse_qual_callback(data: str) -> tuple[str, str] | None:
    parts = data.split(":")
    if len(parts) == 3 and parts[0] == "qual":
        return parts[1], parts[2]
    return None


# ── Keyboard builders ───────────────────────────────────────────


def _t(i18n: Any | None, key: str, fallback: str) -> str:
    if i18n is None:
        return fallback
    return i18n.get(key)


def build_goal_keyboard(i18n: Any | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-goal-buy", "Покупка"),
                    callback_data="qual:goal:buy",
                ),
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-goal-rent", "Аренда"),
                    callback_data="qual:goal:rent",
                ),
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-goal-consult", "Консультация"),
                    callback_data="qual:goal:consult",
                ),
            ]
        ]
    )


def build_budget_keyboard(i18n: Any | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-budget-low", "до 50к€"),
                    callback_data="qual:budget:low",
                ),
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-budget-mid", "50-100к€"),
                    callback_data="qual:budget:mid",
                ),
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-budget-high", "100к€+"),
                    callback_data="qual:budget:high",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-budget-unknown", "Пока не знаю"),
                    callback_data="qual:budget:unknown",
                ),
            ],
        ]
    )


def build_contact_keyboard(i18n: Any | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-contact-chat", "Написать сейчас"),
                    callback_data="qual:contact:chat",
                ),
                InlineKeyboardButton(
                    text=_t(i18n, "handoff-contact-phone", "Оставить номер"),
                    callback_data="qual:contact:phone",
                ),
            ]
        ]
    )


# ── Start qualification ─────────────────────────────────────────


async def start_qualification(
    message_or_callback: Any,
    i18n: Any | None = None,
) -> None:
    """Send first qualification step (goal selection)."""
    text = _t(i18n, "handoff-qual-prompt", "Чтобы менеджер сразу помог:")
    kb = build_goal_keyboard(i18n)
    if hasattr(message_or_callback, "message"):
        # CallbackQuery
        await message_or_callback.message.answer(text, reply_markup=kb)
    else:
        await message_or_callback.answer(text, reply_markup=kb)


# ── Qualification callback handler ──────────────────────────────

# Stores in-progress qualification per user.  Cleared on completion.
# Key: user_id → {"goal": ..., "budget": ...}
_qual_cache: dict[int, dict[str, str]] = {}


async def on_qual_callback(
    callback: CallbackQuery,
    i18n: Any | None = None,
    **kwargs: Any,
) -> None:
    """Handle qual:goal/budget callback queries — advance through steps."""
    parsed = parse_qual_callback(callback.data or "")
    if not parsed:
        return
    step, value = parsed
    user_id = callback.from_user.id

    msg = callback.message
    if msg is None or not hasattr(msg, "edit_text"):
        await callback.answer()
        return

    if user_id not in _qual_cache:
        _qual_cache[user_id] = {}
    _qual_cache[user_id][step] = value

    if step == "goal":
        text = _t(i18n, "handoff-budget-prompt", "Какой бюджет?")
        kb = build_budget_keyboard(i18n)
        await msg.edit_text(text, reply_markup=kb)
    elif step == "budget":
        text = _t(i18n, "handoff-contact-prompt", "Как удобнее связаться?")
        kb = build_contact_keyboard(i18n)
        await msg.edit_text(text, reply_markup=kb)

    await callback.answer()


def get_user_qualification(user_id: int) -> dict[str, str]:
    """Retrieve and clear cached qualification data for a user."""
    return _qual_cache.pop(user_id, {})


# ── Router factory ──────────────────────────────────────────────


def create_handoff_router() -> Router:
    """Create router for handoff qualification callbacks (goal + budget only)."""
    router = Router(name="handoff_qualification")
    router.callback_query(F.data.startswith("qual:goal:") | F.data.startswith("qual:budget:"))(
        on_qual_callback
    )
    return router
