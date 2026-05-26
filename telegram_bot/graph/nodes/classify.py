"""classify_node — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.graph.nodes.classify`
as part of the reverse-layering Slice B (#2049 / #1948). This module
remains so that existing ``from telegram_bot.graph.nodes.classify import …``
imports across ``telegram_bot/``, ``tests/``, and the rest of the repo
continue to work unchanged.
"""

from src.runtime.graph.nodes.classify import (
    CHITCHAT,
    CHITCHAT_RESPONSES,
    ENTITY,
    FAQ,
    GENERAL,
    OFF_TOPIC,
    OFF_TOPIC_RESPONSES,
    STRUCTURED,
    _get_chitchat_response,
    classify_node,
    classify_query,
)


__all__ = [
    "CHITCHAT",
    "CHITCHAT_RESPONSES",
    "ENTITY",
    "FAQ",
    "GENERAL",
    "OFF_TOPIC",
    "OFF_TOPIC_RESPONSES",
    "STRUCTURED",
    "_get_chitchat_response",
    "classify_node",
    "classify_query",
]
