"""Cache check and store nodes for RAG LangGraph pipeline.

cache_check_node: compute embedding, check semantic cache, return cache_hit.
cache_store_node: store response in semantic cache + conversation history.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


@observe(name="node-cache-check")
async def cache_check_node(
    state: dict[str, Any],
    *,
    cache: Any,
    embeddings: Any,
) -> dict[str, Any]:
    """Check semantic cache. Compute embedding if not cached.

    Args:
        state: RAGState dict
        cache: CacheLayerManager instance
        embeddings: BGEM3Embeddings instance (for aembed_query)

    Returns:
        State update with cache_hit, cached_response, query_embedding
    """
    query = (
        state["messages"][-1].content
        if hasattr(state["messages"][-1], "content")
        else state["messages"][-1]["content"]
    )
    query_type = state.get("query_type", "GENERAL")

    start = time.perf_counter()

    # Step 1: Get or compute dense embedding (prefer hybrid for efficiency)
    embedding = await cache.get_embedding(query)
    if embedding is None:
        if hasattr(embeddings, "aembed_hybrid"):
            # Hybrid: get both dense + sparse in one call, cache both
            embedding, sparse = await embeddings.aembed_hybrid(query)
            await cache.store_embedding(query, embedding)
            await cache.store_sparse_embedding(query, sparse)
        else:
            embedding = await embeddings.aembed_query(query)
            await cache.store_embedding(query, embedding)

    # Step 2: Check semantic cache with query-type threshold
    cached = await cache.check_semantic(
        query=query,
        vector=embedding,
        query_type=query_type,
    )

    latency = time.perf_counter() - start

    if cached:
        logger.info("cache_check HIT (%.3fs, type=%s)", latency, query_type)
        return {
            "cache_hit": True,
            "cached_response": cached,
            "query_embedding": embedding,
            "response": cached,
            "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
        }

    logger.info("cache_check MISS (%.3fs, type=%s)", latency, query_type)
    return {
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": embedding,
        "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
    }


@observe(name="node-cache-store")
async def cache_store_node(
    state: dict[str, Any],
    *,
    cache: Any,
    event_stream: Any | None = None,
) -> dict[str, Any]:
    """Store response in semantic cache and conversation history.

    Args:
        state: RAGState dict (must have response, query_embedding, query_type)
        cache: CacheLayerManager instance
        event_stream: Optional PipelineEventStream for observability logging

    Returns:
        State update (pass-through response)
    """
    response = state.get("response", "")
    embedding = state.get("query_embedding")
    query_type = state.get("query_type", "GENERAL")
    query = (
        state["messages"][-1].content
        if hasattr(state["messages"][-1], "content")
        else state["messages"][-1]["content"]
    )
    user_id = state.get("user_id", 0)

    # Store in semantic cache if we have both response and embedding
    if response and embedding:
        await cache.store_semantic(
            query=query,
            response=response,
            vector=embedding,
            query_type=query_type,
        )

        # Store conversation messages (single pipeline round-trip)
        await cache.store_conversation_batch(
            user_id=user_id,
            messages=[("user", query), ("assistant", response)],
        )

        logger.info("cache_store: stored response + conversation (type=%s)", query_type)

        # Log pipeline result event (fire-and-forget, never blocks main flow)
        if event_stream is not None:
            latency_stages = state.get("latency_stages", {})
            total_latency = sum(latency_stages.values()) if latency_stages else 0
            await event_stream.log_event(
                "pipeline_result",
                {
                    "query": query[:200],
                    "query_type": query_type,
                    "latency_ms": round(total_latency * 1000) if total_latency else 0,
                    "cache_hit": state.get("cache_hit", False),
                    "search_count": state.get("search_results_count", 0),
                    "rerank_applied": state.get("rerank_applied", False),
                    "node_name": "cache_store",
                    "user_id": user_id,
                },
            )

    return {"response": response}
