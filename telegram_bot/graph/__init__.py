"""Legacy compatibility layer — not an active public API surface.

ARCH-16 decision (#2697): ``telegram_bot/graph/`` is retained as a
compatibility façade, **not** as a competing text runtime.

* ``build_graph`` / ``GraphConfig`` / ``RAGState`` / ``make_initial_state``
  are re-exported here so that the voice path (``telegram_bot/bot.py``) and
  the ``PYTEST_LEGACY_GRAPH_PATHS`` test lane continue to work without changes.
* The canonical text-RAG path is ``src/core/assistant.py`` +
  ``src/runtime/pipeline/assistant_pipeline.py``.
* Do **not** add new callers of these exports; route new work through the
  assistant-core path instead.
"""

from src.runtime.graph.config import GraphConfig
from src.runtime.graph.state import RAGState, make_initial_state

from .graph import build_graph


__all__ = ["GraphConfig", "RAGState", "build_graph", "make_initial_state"]
