"""Runtime-owned graph factory surface.

The reusable runtime package must not point back to the Telegram adapter as its
factory default. This module provides the neutral default import target for
``src.runtime.graph.builder``. Adapter-specific graph assembly can still be
selected explicitly with ``RAG_GRAPH_FACTORY``.
"""

from __future__ import annotations

from typing import Any


class RuntimeGraphFactoryUnavailable(RuntimeError):
    """Raised when the neutral runtime factory is called without an adapter."""


def build_graph(**kwargs: Any) -> Any:
    """Build the default runtime graph.

    The legacy LangGraph graph still has transport-specific nodes. Until those
    nodes are fully migrated into ``src.runtime.graph.nodes``, callers that need
    the adapter graph must set ``RAG_GRAPH_FACTORY`` explicitly. Keeping this
    neutral callable in ``src.runtime`` removes the runtime -> adapter default
    dependency while preserving the builder's import contract.
    """

    raise RuntimeGraphFactoryUnavailable(
        "The default runtime graph factory is intentionally adapter-neutral. "
        "Set RAG_GRAPH_FACTORY to an application graph factory to build a graph."
    )


__all__ = ["RuntimeGraphFactoryUnavailable", "build_graph"]
