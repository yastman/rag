"""Cache check and store nodes for RAG LangGraph pipeline.

cache_check_node: compute embedding, check semantic cache, return cache_hit.
cache_store_node: store response in semantic cache + conversation history.
"""

from __future__ import annotations

import logging
import time
from typing import Any


logger = logging.getLogger(__name__)


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

    start = time.time()

    # Step 1: Get or compute dense embedding
    embedding = await cache.get_embedding(query)
    if embedding is None:
        embedding = await embeddings.aembed_query(query)
        await cache.store_embedding(query, embedding)

    # Step 2: Check semantic cache with query-type threshold
    cached = await cache.check_semantic(
        query=query,
        vector=embedding,
        query_type=query_type,
    )

    latency = (time.time() - start) * 1000

    if cached:
        logger.info("cache_check HIT (%.0fms, type=%s)", latency, query_type)
        return {
            "cache_hit": True,
            "cached_response": cached,
            "query_embedding": embedding,
            "response": cached,
            "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
        }

    logger.info("cache_check MISS (%.0fms, type=%s)", latency, query_type)
    return {
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": embedding,
        "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
    }


async def cache_store_node(
    state: dict[str, Any],
    *,
    cache: Any,
) -> dict[str, Any]:
    """Store response in semantic cache and conversation history.

    Args:
        state: RAGState dict (must have response, query_embedding, query_type)
        cache: CacheLayerManager instance

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

    return {"response": response}
