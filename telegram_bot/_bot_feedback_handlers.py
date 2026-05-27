"""Feedback callback handlers extracted from ``telegram_bot/bot.py``.

Slice 2 PR-9a of the bot.py decomposition plan
(``docs/engineering/bot-decomposition-plan-2026-05-27.md``, parent
#1265 / child #2048). Owns the three feedback-related callback
handlers:

* :func:`handle_feedback` — like / dislike / done routing.
* :func:`handle_feedback_reason` — dislike reason selection.
* :func:`clear_feedback_confirmation_later` — async cleanup of the
  confirmation keyboard after a TTL.

The functions are module-level and take the ``PropertyBot`` instance
as the first positional argument. ``PropertyBot.handle_feedback`` /
``handle_feedback_reason`` / ``_clear_feedback_confirmation_later``
remain on the class as thin delegates so:

* aiogram dispatcher registration in ``_register_handlers`` keeps
  binding ``self.handle_feedback`` directly (the dispatcher captures
  the bound method);
* the existing ``tests/unit/test_bot_handlers.py`` suite keeps
  resolving ``bot.handle_feedback`` / ``bot._clear_feedback_confirmation_later``
  unchanged.

Module-level imports are kept to stdlib + the small set of
``telegram_bot`` helpers each handler reaches for; the heavier
``langchain``/``langgraph`` imports stay inside ``bot.py``. The
per-extraction contract (no aiogram-removal, no behaviour drift) is
pinned by ``tests/contract/test_bot_feedback_handlers_extraction_contract.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.callback_data import FeedbackCB, FeedbackReasonCB
from telegram_bot.observability import get_langfuse_client


if TYPE_CHECKING:  # pragma: no cover — typing-only
    from aiogram.types import CallbackQuery

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)


# Time-to-live for the post-feedback confirmation keyboard before it is
# cleared. Mirrors the ``_FEEDBACK_CONFIRMATION_TTL_S`` constant in
# ``bot.py`` so the two callsites stay aligned without an extra import.
FEEDBACK_CONFIRMATION_TTL_S = 5.0


async def handle_feedback(
    bot: PropertyBot,
    callback: CallbackQuery,
    callback_data: FeedbackCB | None = None,
) -> None:
    """Handle feedback like/dislike/done callback (#229, #755).

    Supports CallbackData injection from aiogram DI, with legacy string
    fallback for backward compatibility with tests and old-format
    buttons.
    """
    from telegram_bot.feedback import (
        build_dislike_reason_keyboard,
        build_feedback_confirmation,
        parse_feedback_callback,
    )

    if callback_data is not None:
        # New CallbackData path (aiogram DI injection)
        if callback_data.action == "done":
            await callback.answer()
            return
        if callback_data.action == "dislike":
            # Step 1: show reason keyboard, score written in handle_feedback_reason
            await callback.answer()
            try:
                msg = callback.message
                if msg is not None and hasattr(msg, "edit_reply_markup"):
                    await msg.edit_reply_markup(
                        reply_markup=build_dislike_reason_keyboard(callback_data.trace_id)
                    )
            except Exception:
                logger.debug("Failed to show dislike reason keyboard", exc_info=True)
            return
        # "like" action: write score below
        value: float = 1.0
        trace_id: str = callback_data.trace_id
        reason: str | None = None
    else:
        # Legacy fallback (tests and old-format buttons: fb:1/0:, fb:r:)
        data = callback.data or ""
        if data in ("fb:done", "fb:done:"):
            await callback.answer()
            return
        parsed = parse_feedback_callback(data)
        if parsed is None:
            await callback.answer()
            return
        value, trace_id, reason = parsed

        # Legacy dislike without reason → show reason keyboard
        if value == 0.0 and reason is None:
            await callback.answer()
            try:
                msg = callback.message
                if msg is not None and hasattr(msg, "edit_reply_markup"):
                    await msg.edit_reply_markup(
                        reply_markup=build_dislike_reason_keyboard(trace_id)
                    )
            except Exception:
                logger.debug("Failed to show dislike reason keyboard", exc_info=True)
            return

    # Write score (like, or legacy reason path)
    await callback.answer("Спасибо за отзыв!")
    user_id = callback.from_user.id if callback.from_user else 0

    try:
        lf_client = get_langfuse_client()
        if lf_client is not None:
            lf_client.create_score(
                trace_id=trace_id,
                name="user_feedback",
                value=value,
                data_type="NUMERIC",
                comment=f"user_id:{user_id}",
                score_id=f"{trace_id}-user_feedback",
            )
            if reason is not None:
                lf_client.create_score(
                    trace_id=trace_id,
                    name="user_feedback_reason",
                    value=reason,
                    data_type="CATEGORICAL",
                    comment=f"user_id:{user_id}",
                    score_id=f"{trace_id}-user_feedback_reason",
                )
    except Exception:
        logger.warning("Failed to write feedback score to Langfuse", exc_info=True)

    # Update keyboard to confirmation
    liked = value > 0
    try:
        msg = callback.message
        if msg is not None and hasattr(msg, "edit_reply_markup"):
            await msg.edit_reply_markup(reply_markup=build_feedback_confirmation(liked=liked))
            cleanup_task = asyncio.create_task(
                clear_feedback_confirmation_later(msg, FEEDBACK_CONFIRMATION_TTL_S)
            )
            cleanup_task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)
    except Exception:
        logger.debug("Failed to update feedback keyboard", exc_info=True)


async def handle_feedback_reason(
    bot: PropertyBot,
    callback: CallbackQuery,
    callback_data: FeedbackReasonCB,
) -> None:
    """Handle dislike reason selection callback (#755)."""
    from telegram_bot.feedback import _REASON_CODES, build_feedback_confirmation

    reason = _REASON_CODES.get(callback_data.code)
    if reason is None:
        await callback.answer()
        return

    trace_id = callback_data.trace_id
    await callback.answer("Спасибо за отзыв!")
    user_id = callback.from_user.id if callback.from_user else 0

    try:
        lf_client = get_langfuse_client()
        if lf_client is not None:
            lf_client.create_score(
                trace_id=trace_id,
                name="user_feedback",
                value=0.0,
                data_type="NUMERIC",
                comment=f"user_id:{user_id}",
                score_id=f"{trace_id}-user_feedback",
            )
            lf_client.create_score(
                trace_id=trace_id,
                name="user_feedback_reason",
                value=reason,
                data_type="CATEGORICAL",
                comment=f"user_id:{user_id}",
                score_id=f"{trace_id}-user_feedback_reason",
            )
    except Exception:
        logger.warning("Failed to write feedback reason score to Langfuse", exc_info=True)

    try:
        msg = callback.message
        if msg is not None and hasattr(msg, "edit_reply_markup"):
            await msg.edit_reply_markup(reply_markup=build_feedback_confirmation(liked=False))
            cleanup_task = asyncio.create_task(
                clear_feedback_confirmation_later(msg, FEEDBACK_CONFIRMATION_TTL_S)
            )
            cleanup_task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)
    except Exception:
        logger.debug("Failed to update feedback keyboard after reason", exc_info=True)


async def clear_feedback_confirmation_later(
    message: Any,
    delay_s: float = FEEDBACK_CONFIRMATION_TTL_S,
) -> None:
    """Clear feedback confirmation keyboard after a short delay."""
    await asyncio.sleep(delay_s)
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("Failed to clear feedback confirmation keyboard", exc_info=True)


__all__ = (
    "FEEDBACK_CONFIRMATION_TTL_S",
    "clear_feedback_confirmation_later",
    "handle_feedback",
    "handle_feedback_reason",
)
