"""guard_node — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.graph.nodes.guard`
as part of the reverse-layering Slice B (#2049 / #1948). This module
remains so that existing ``from telegram_bot.graph.nodes.guard import …``
imports across ``telegram_bot/``, ``tests/``, and the rest of the repo
continue to work unchanged.
"""

from src.runtime.graph.nodes.guard import (
    _BLOCKED_RESPONSE,
    _INJECTION_THRESHOLD,
    INJECTION_PATTERNS,
    detect_injection,
    guard_node,
)


__all__ = [
    "INJECTION_PATTERNS",
    "_BLOCKED_RESPONSE",
    "_INJECTION_THRESHOLD",
    "detect_injection",
    "guard_node",
]
