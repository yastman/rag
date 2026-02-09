"""RAG LangGraph pipeline — graph assembly.

Builds the full StateGraph with all nodes and conditional edges.
"""

from __future__ import annotations

import functools
from typing import Any

from langgraph.graph import END, START, StateGraph

from telegram_bot.graph.edges import route_by_query_type, route_cache, route_grade
from telegram_bot.graph.state import RAGState


def build_graph(
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
    message: Any | None = None,
) -> Any:
    """Build and compile the RAG StateGraph.

    Args:
        cache: CacheLayerManager instance
        embeddings: BGEM3Embeddings instance
        sparse_embeddings: BGEM3SparseEmbeddings instance
        qdrant: QdrantService instance
        reranker: Optional ColbertRerankerService
        llm: Optional LLM instance (defaults via GraphConfig)
        message: Optional aiogram Message for respond_node

    Returns:
        Compiled StateGraph ready for .ainvoke()
    """
    from telegram_bot.graph.nodes.cache import cache_check_node, cache_store_node
    from telegram_bot.graph.nodes.classify import classify_node
    from telegram_bot.graph.nodes.generate import generate_node
    from telegram_bot.graph.nodes.grade import grade_node
    from telegram_bot.graph.nodes.rerank import rerank_node
    from telegram_bot.graph.nodes.rewrite import rewrite_node

    workflow = StateGraph(RAGState)

    # Add nodes — wrap those that need injected deps via functools.partial
    workflow.add_node("classify", classify_node)  # type: ignore[type-var]

    workflow.add_node(
        "cache_check",
        functools.partial(cache_check_node, cache=cache, embeddings=embeddings),
    )

    workflow.add_node(
        "retrieve",
        functools.partial(
            retrieve_node_wrapper,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        ),
    )

    workflow.add_node("grade", grade_node)  # type: ignore[type-var]

    workflow.add_node(
        "rerank",
        functools.partial(rerank_node, reranker=reranker),
    )

    workflow.add_node("generate", generate_node)

    workflow.add_node(
        "rewrite",
        functools.partial(rewrite_node, llm=llm),
    )

    workflow.add_node(
        "cache_store",
        functools.partial(cache_store_node, cache=cache),
    )

    workflow.add_node(
        "respond",
        _make_respond_node(message),
    )

    # Edges
    workflow.add_edge(START, "classify")

    workflow.add_conditional_edges(
        "classify",
        route_by_query_type,
        {
            "respond": "respond",
            "cache_check": "cache_check",
        },
    )

    workflow.add_conditional_edges(
        "cache_check",
        route_cache,
        {
            "respond": "respond",
            "retrieve": "retrieve",
        },
    )

    workflow.add_edge("retrieve", "grade")

    workflow.add_conditional_edges(
        "grade",
        route_grade,
        {
            "rerank": "rerank",
            "rewrite": "rewrite",
            "generate": "generate",
        },
    )

    workflow.add_edge("rerank", "generate")
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", "cache_store")
    workflow.add_edge("cache_store", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile()


async def retrieve_node_wrapper(
    state: dict[str, Any],
    *,
    cache: Any,
    sparse_embeddings: Any,
    qdrant: Any,
) -> dict[str, Any]:
    """Wrapper for retrieve_node to match functools.partial signature."""
    from telegram_bot.graph.nodes.retrieve import retrieve_node

    return await retrieve_node(
        state,
        cache=cache,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
    )


def _make_respond_node(message: Any | None):
    """Create respond_node with message injected into state."""
    from telegram_bot.graph.nodes.respond import respond_node

    if message is None:
        return respond_node

    async def respond_with_message(state: dict[str, Any]) -> dict[str, Any]:
        state_with_msg = {**state, "message": message}
        return await respond_node(state_with_msg)

    return respond_with_message
