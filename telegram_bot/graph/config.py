"""GraphConfig — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.graph.config` as
the second slice of the reverse-layering fix (#2045 / #2049). This
module remains so that existing ``from telegram_bot.graph.config import …``
imports across ``telegram_bot/``, ``tests/``, and the rest of the repo
continue to work unchanged.
"""

from src.runtime.graph.config import GraphConfig


__all__ = ["GraphConfig"]
