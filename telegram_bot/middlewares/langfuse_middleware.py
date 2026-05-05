"""Langfuse context middleware — universal trace root for Telegram updates."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from telegram_bot.observability import get_client, propagate_attributes
from telegram_bot.tracing_context import classify_action, make_session_id


logger = logging.getLogger(__name__)


def _extract_event_input(event: TelegramObject, action_type: str) -> dict[str, Any]:
    """Build a safe, concise input dict from a Telegram event.

    PII masking is delegated to the Langfuse SDK mask layer; this helper only
    extracts coarse action/text metadata so the root trace is not empty.
    """
    if isinstance(event, Message):
        text = event.text or event.caption or ""
        return {
            "action": action_type,
            "content_type": event.content_type,
            "text_preview": text[:500] if text else "",
        }
    if isinstance(event, CallbackQuery):
        return {
            "action": action_type,
            "callback_data": (event.data or "")[:200],
        }
    return {"action": action_type}


class LangfuseContextMiddleware(BaseMiddleware):
    """Create Langfuse trace context for every Telegram update.

    Opens a root observation via ``start_as_current_observation`` and propagates
    ``session_id``, ``user_id`` and ``tags`` to all child observations.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lf = get_client()
        if lf is None:
            return await handler(event, data)

        user = data.get("event_from_user")
        chat = data.get("event_chat")
        user_id = getattr(user, "id", None)
        chat_id = getattr(chat, "id", None) or user_id or "unknown"
        session_id = make_session_id("chat", chat_id)
        action_type = classify_action(event, data)

        with (
            lf.start_as_current_observation(
                as_type="span",
                name=f"telegram-{action_type}",
                input=_extract_event_input(event, action_type),
            ),
            propagate_attributes(
                session_id=session_id,
                user_id=str(user_id) if user_id is not None else None,
                tags=["telegram", action_type],
            ),
        ):
            return await handler(event, data)
