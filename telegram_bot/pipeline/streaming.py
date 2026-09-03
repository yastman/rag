"""Draft-id helper extracted from ``telegram_bot/bot.py`` (#1265).

Slice 1 PR-4 of the published bot.py decomposition plan.

The agent streaming facade (``_stream_agent_to_draft``,
``_extract_stream_chunk_text``, ``_AGENT_DRAFT_INTERVAL``) was removed in
#3218: its only caller was the supervisor recovery wrapper deleted with the
imperative agent facade (#3216), so the helper existed only for
agent/checkpointer compatibility. Q&A responses are sent once via plain
``send_message``; no token-level drafting remains.

Owned helper:

  - ``_new_draft_id`` — 31-bit signed-int draft id generator, still used by
    ``pipeline/supervisor.py::_send_core_response`` for the one-shot draft
    finalize message id.
"""

from __future__ import annotations

import secrets


def _new_draft_id() -> int:
    """Generate a positive 31-bit draft id for `bot.send_message_draft`.

    Bot API ``sendMessageDraft`` accepts arbitrary 32-bit positive integers
    as the draft id; we keep the value within signed-int32 range so it
    serialises cleanly across the aiogram client and the Bot API JSON wire
    format. Moved here from ``services/draft_streamer.py`` (#1671).
    """
    return secrets.randbelow(2**31 - 1) + 1
