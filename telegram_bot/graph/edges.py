"""Conditional edge functions — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.graph.edges` as
part of the reverse-layering Slice A (#1948 / #2049). This module remains
so that existing ``from telegram_bot.graph.edges import …`` imports
continue to work unchanged.
"""

from src.runtime.graph.edges import (
    route_after_guard,
    route_by_query_type,
    route_cache,
    route_grade,
    route_start,
)


__all__ = [
    "route_after_guard",
    "route_by_query_type",
    "route_cache",
    "route_grade",
    "route_start",
]
