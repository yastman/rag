"""RAGState schema for LangGraph pipeline — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.graph.state` as
the first slice of the reverse-layering fix (#2049 / #2045). This module
remains so that existing ``from telegram_bot.graph.state import …``
imports across ``telegram_bot/``, ``tests/``, and the rest of the repo
continue to work unchanged.
"""

from src.runtime.graph.state import RAGState, make_initial_state


__all__ = ["RAGState", "make_initial_state"]
