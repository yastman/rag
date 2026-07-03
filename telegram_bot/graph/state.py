"""Compatibility shim — re-exports from src.runtime.graph.state.

The canonical module moved during P17; this shim lets legacy test imports
like ``from telegram_bot.graph.state import make_initial_state`` continue
to work without change.
"""

from src.runtime.graph.state import RAGState, make_initial_state


__all__ = ["RAGState", "make_initial_state"]
