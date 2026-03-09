"""Native Telegram streaming via sendMessageDraft (Bot API 9.5+)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from aiogram import Bot


class DraftStreamer:
    """Streams LLM output to user via sendMessageDraft + finalize with sendMessage."""

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        thread_id: int | None = None,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._draft_id = random.randint(1, 2**31 - 1)

    async def send_chunk(self, accumulated_text: str) -> None:
        """Send intermediate draft (animated on client side)."""
        kwargs: dict[str, Any] = {
            "chat_id": self._chat_id,
            "draft_id": self._draft_id,
            "text": accumulated_text,
        }
        if self._thread_id is not None:
            kwargs["message_thread_id"] = self._thread_id
        await self._bot.send_message_draft(**kwargs)

    async def finalize(self, text: str, **send_kwargs: Any) -> Any:
        """Send final message (replaces draft on client)."""
        kwargs: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text,
            **send_kwargs,
        }
        if self._thread_id is not None:
            kwargs["message_thread_id"] = self._thread_id
        return await self._bot.send_message(**kwargs)
