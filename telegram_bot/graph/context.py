"""GraphContext — run-scoped dependency container for LangGraph Runtime.

Passed via ``context_schema=GraphContext`` to ``StateGraph`` and injected
into nodes as ``runtime: Runtime[GraphContext]``.
"""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class GraphContext(TypedDict, total=False):
    """Dependencies injected into RAG pipeline nodes via LangGraph Runtime.

    All fields are optional at the TypedDict level; build_graph always provides
    the required ones (cache, embeddings, sparse_embeddings, qdrant).
    """

    cache: Any
    """CacheLayerManager instance."""

    embeddings: Any
    """BGEM3Embeddings instance for dense vectors."""

    sparse_embeddings: Any
    """BGEM3SparseEmbeddings instance for sparse vectors."""

    qdrant: Any
    """QdrantService instance for hybrid search."""

    reranker: Any
    """Optional reranker hook; deprecated ColbertRerankerService inputs are ignored."""

    llm: Any
    """Optional LLM/OpenAI async client for rewrite/transcribe."""

    event_stream: Any
    """Optional PipelineEventStream for observability logging."""

    guard_mode: str
    """Guard mode: 'hard' | 'soft' | 'log'."""

    classifier: Any
    """Optional SemanticClassifier instance."""
