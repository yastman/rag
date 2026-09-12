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
``langchain``/``langgraph`` imports stay inside ``bot.py``. Feedback
callback behavior is pinned by ``tests/unit/test_bot_feedback_integration.py``
and ``tests/unit/test_feedback_handler.py``; the dispatcher-level feedback
observability capability (#3422) is pinned by
``tests/e2e/test_feedback_observability_capability.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.callback_data import FeedbackCB, FeedbackReasonCB
from telegram_bot.observability.context import make_session_id


if TYPE_CHECKING:  # pragma: no cover — typing-only
    from aiogram.types import CallbackQuery

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)


# Time-to-live for the post-feedback confirmation keyboard before it is
# cleared. Mirrors the ``_FEEDBACK_CONFIRMATION_TTL_S`` constant in
# ``bot.py`` so the two callsites stay aligned without an extra import.
FEEDBACK_CONFIRMATION_TTL_S = 5.0


async def _persist_feedback(
    feedback_store: Any | None,
    *,
    callback: CallbackQuery,
    request_id: str,
    action: str,
    reason: str | None,
) -> None:
    """Write one redacted feedback record via the configured writer (#3422).

    The store's append signature is an explicit allowlist (user/session/
    request linkage plus the enumerated action and the fixed reason code), so
    token, phone, or raw-prompt content cannot reach the record. A storage
    failure keeps the safe UI: the structured error carries only the linkage
    fields and the exception type — never banned content.
    """
    if feedback_store is None or not request_id:
        return
    chat = getattr(getattr(callback, "message", None), "chat", None)
    chat_id = getattr(chat, "id", None)
    session_id = make_session_id("chat", chat_id) if chat_id is not None else ""
    user_id = int(getattr(callback.from_user, "id", 0) or 0)
    try:
        await feedback_store.append(
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            action=action,
            reason=reason,
        )
    except Exception as exc:
        logger.error(
            "Feedback store write failed: %s",
            type(exc).__name__,
            exc_info=True,
            extra={"request_id": request_id, "action": action},
        )


async def handle_feedback(
    bot: PropertyBot,
    callback: CallbackQuery,
    callback_data: FeedbackCB | None = None,
    feedback_store: Any | None = None,
) -> None:
    """Handle feedback like/dislike/done callback (#229, #755).

    Supports CallbackData injection from aiogram DI, with legacy string
    fallback for backward compatibility with tests and old-format
    buttons. ``feedback_store`` arrives via aiogram workflow-data DI
    (``dp["feedback_store"]``, wired by ``setup_postgres``, #3422).
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
        # "like" action: acknowledge below
        value: float = 1.0
        trace_id = callback_data.trace_id
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

    # One redacted feedback record for the accepted feedback (#3422); a
    # storage failure must not break the safe UI below.
    await _persist_feedback(
        feedback_store,
        callback=callback,
        request_id=trace_id,
        action="like" if value > 0 else "dislike",
        reason=reason,
    )

    # Feedback acknowledged (scoring removed in #2844, #2969).
    await callback.answer("Спасибо за отзыв!")

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
    feedback_store: Any | None = None,
) -> None:
    """Handle dislike reason selection callback (#755)."""
    from telegram_bot.feedback import _REASON_CODES, build_feedback_confirmation

    reason = _REASON_CODES.get(callback_data.code)
    if reason is None:
        await callback.answer()
        return

    # The reason refines the single record for this request (#3422).
    await _persist_feedback(
        feedback_store,
        callback=callback,
        request_id=callback_data.trace_id,
        action="dislike",
        reason=reason,
    )

    await callback.answer("Спасибо за отзыв!")

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
