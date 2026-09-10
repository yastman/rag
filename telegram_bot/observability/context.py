"""Shared tracing helpers — unified session ID.

Moved from ``telegram_bot/tracing_context.py`` into this package
(card_265772dd6bd4). The old module is kept as a backward-compat shim.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime


def make_session_id(session_type: str, identifier: int | str) -> str:
    """Create unified session_id format: {type}-{hash}-{YYYYMMDD}."""
    id_hash = hashlib.sha256(str(identifier).encode()).hexdigest()[:8]
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    return f"{session_type}-{id_hash}-{date_str}"


__all__ = [
    "make_session_id",
]
