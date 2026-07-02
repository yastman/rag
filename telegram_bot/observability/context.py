"""Shared tracing helpers — session ID and action classification.

Moved from ``telegram_bot/tracing_context.py`` into this package
(card_265772dd6bd4). The old module is kept as a backward-compat shim.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from aiogram.types import CallbackQuery, Message


logger = logging.getLogger(__name__)


def make_session_id(session_type: str, identifier: int | str) -> str:
    """Create unified session_id format: {type}-{hash}-{YYYYMMDD}."""
    id_hash = hashlib.sha256(str(identifier).encode()).hexdigest()[:8]
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    return f"{session_type}-{id_hash}-{date_str}"


def classify_action(event: Any, _data: dict[str, Any] | None = None) -> str:
    """Classify a Telegram event into an action type for tracing."""
    if isinstance(event, CallbackQuery):
        cb_data = event.data or ""
        if ":" in cb_data:
            return f"callback-{cb_data.split(':')[0]}"
        return "callback"
    if isinstance(event, Message):
        if getattr(event, "content_type", None) == "voice":
            return "rag-voice"
        text = event.text or ""
        if text.startswith("/"):
            cmd = text.split()[0].split("@")[0].lstrip("/")
            return f"cmd-{cmd}"
        return "message"
    return "update"


__all__ = [
    "classify_action",
    "make_session_id",
]
