"""Pure streaming/draft helpers extracted from ``telegram_bot/bot.py`` (#1265).

Slice 1 PR-4 of the published bot.py decomposition plan.

Owns the SDK-only streaming bridge between LangGraph's ``agent.astream(...)``
and Telegram's ``bot.send_message_draft(...)`` API. Module-level imports are
restricted to stdlib so this module can be imported by tests and lightweight
runtime adapters without pulling the full bot stack (no aiogram, no
langgraph, no langchain, no fastapi).

Owned helpers (verbatim, byte-for-byte semantics with the pre-extract
``bot.py`` definitions; pinned by
``tests/contract/test_bot_streaming_extraction_contract.py``):

  - ``_new_draft_id``            — 31-bit signed-int draft id generator.
  - ``_stream_agent_to_draft``   — agent.astream() → bot.send_message_draft.
  - ``_extract_stream_chunk_text`` — pull human text from a LangChain chunk.

Owned constant:

  - ``_AGENT_DRAFT_INTERVAL`` — minimum seconds between sendMessageDraft
    calls. Bumping it reduces Telegram API pressure but increases user-
    perceived latency between visible token bursts.
"""

from __future__ import annotations

import contextlib
import secrets
import time
from typing import Any


_AGENT_DRAFT_INTERVAL: float = 0.2  # seconds between sendMessageDraft calls


def _new_draft_id() -> int:
    """Generate a positive 31-bit draft id for `bot.send_message_draft`.

    Bot API ``sendMessageDraft`` accepts arbitrary 32-bit positive integers
    as the draft id; we keep the value within signed-int32 range so it
    serialises cleanly across the aiogram client and the Bot API JSON wire
    format. Moved here from ``services/draft_streamer.py`` (#1671) so the
    streaming path stays SDK-only — direct ``bot.send_message_draft(...)``
    calls plus ``agent.astream(stream_mode=[...])`` from LangGraph, no
    custom abstraction in between.
    """
    return secrets.randbelow(2**31 - 1) + 1


async def _stream_agent_to_draft(
    agent: Any,
    payload: dict[str, Any],
    config: dict[str, Any],
    bot: Any,
    chat_id: int,
    thread_id: int | None = None,
    *,
    draft_interval: float | None = None,
) -> dict[str, Any]:
    """Stream agent astream() output to Telegram via sendMessageDraft.

    Uses stream_mode=["messages", "values"]:
    - "messages": forward AIMessage content chunks from the "agent" node as drafts.
    - "values": capture final state.

    Only streams content-only chunks (not tool-call chunks). Returns final state dict.
    """
    accumulated = ""
    last_draft = 0.0
    final_state: dict[str, Any] = {}
    draft_id = _new_draft_id()
    interval = _AGENT_DRAFT_INTERVAL if draft_interval is None else draft_interval

    async for mode, data in agent.astream(
        payload, config=config, stream_mode=["messages", "values"]
    ):
        if mode == "values":
            final_state = data
        elif mode == "messages":
            msg, metadata = data
            node = metadata.get("langgraph_node", "")
            if node != "agent":
                continue
            content = getattr(msg, "content", None)
            if not content:
                continue
            # Skip tool-call chunks — they carry tool routing JSON, not user-facing text.
            if getattr(msg, "tool_calls", None):
                continue
            accumulated += content
            now = time.monotonic()
            if now - last_draft >= interval:
                draft_kwargs: dict[str, Any] = {
                    "chat_id": chat_id,
                    "draft_id": draft_id,
                    "text": accumulated,
                }
                if thread_id is not None:
                    draft_kwargs["message_thread_id"] = thread_id
                with contextlib.suppress(Exception):
                    await bot.send_message_draft(**draft_kwargs)
                last_draft = now

    return final_state


def _extract_stream_chunk_text(message_chunk: Any) -> str:
    """Extract human text from LangChain stream chunk payload."""
    text_attr = getattr(message_chunk, "text", None)
    if isinstance(text_attr, str) and text_attr:
        return text_attr

    content = getattr(message_chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                item_text = item.get("text")
                if isinstance(item_text, str):
                    parts.append(item_text)
                continue
            item_text = getattr(item, "text", None)
            if isinstance(item_text, str):
                parts.append(item_text)
        return "".join(parts)
    return ""
