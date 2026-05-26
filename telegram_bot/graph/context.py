"""GraphContext — run-scoped dependency container (back-compat re-export).

The canonical implementation moved to :mod:`src.runtime.graph.context` as
part of the reverse-layering Slice A (#1948 / #2049). This module remains
so that existing ``from telegram_bot.graph.context import …`` imports
continue to work unchanged.
"""

from src.runtime.graph.context import GraphContext


__all__ = ["GraphContext"]
