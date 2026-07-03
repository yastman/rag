"""Checkpointer utility helpers.

Extracted from bot.py to break the circular import between
command_handlers.py and bot.py.
"""

from __future__ import annotations

import inspect
from typing import Any


def _supervisor_thread_id(chat_id: int | str, thread_id: int | None = None) -> str:
    """Build checkpointer thread id for text-agent conversations."""
    if thread_id is not None:
        return f"tg_{chat_id}:{thread_id}"
    return f"tg_{chat_id}"


async def _delete_checkpointer_thread(checkpointer: Any, thread_id: str) -> None:
    """Delete checkpointer thread via async or sync SDK API."""
    adelete_thread = getattr(checkpointer, "adelete_thread", None)
    if callable(adelete_thread):
        await adelete_thread(thread_id)
        return

    delete_thread = getattr(checkpointer, "delete_thread", None)
    if callable(delete_thread):
        result = delete_thread(thread_id)
        if inspect.isawaitable(result):
            await result
        return

    raise AttributeError("checkpointer does not expose delete_thread/adelete_thread")
