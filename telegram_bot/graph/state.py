"""RAGState schema for LangGraph pipeline.

Defines the state passed between graph nodes and the initial state factory.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class RAGState(TypedDict):
    """State schema for the RAG LangGraph pipeline."""

    messages: Annotated[list, add_messages]
    user_id: int
    session_id: str
    query_type: str
    cache_hit: bool
    cached_response: str | None
    query_embedding: list[float] | None
    sparse_embedding: dict[str, Any] | None
    documents: list[dict[str, Any]]
    documents_relevant: bool
    rewrite_count: int
    rewrite_effective: bool
    max_rewrite_attempts: int
    response: str
    latency_stages: dict[str, float]
    search_results_count: int
    rerank_applied: bool
    grade_confidence: float


def make_initial_state(user_id: int, session_id: str, query: str) -> dict[str, Any]:
    """Create initial state for a new RAG pipeline invocation."""
    return {
        "messages": [{"role": "user", "content": query}],
        "user_id": user_id,
        "session_id": session_id,
        "query_type": "",
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": None,
        "sparse_embedding": None,
        "documents": [],
        "documents_relevant": False,
        "rewrite_count": 0,
        "rewrite_effective": True,
        "max_rewrite_attempts": 1,
        "response": "",
        "latency_stages": {},
        "search_results_count": 0,
        "rerank_applied": False,
        "grade_confidence": 0.0,
    }
