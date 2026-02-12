"""Cache check and store nodes for RAG LangGraph pipeline.

cache_check_node: compute embedding, check semantic cache, return cache_hit.
cache_store_node: store response in semantic cache + conversation history.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

# Only these query types use semantic cache (check + store).
# Context-sensitive types like GENERAL bypass semantic cache entirely.
CACHEABLE_QUERY_TYPES: frozenset[str] = frozenset({"FAQ", "ENTITY", "STRUCTURED"})


@observe(name="node-cache-check", capture_input=False, capture_output=False)
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
    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )
    query_type = state.get("query_type", "GENERAL")

    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "query_type": query_type,
        }
    )

    start = time.perf_counter()

    # Step 1: Get or compute dense embedding (prefer hybrid for efficiency)
    embedding = await cache.get_embedding(query)
    embeddings_cache_hit = embedding is not None
    if embedding is None:
        _has_hybrid = callable(
            getattr(embeddings, "aembed_hybrid", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid)
        if _has_hybrid:
            # Hybrid: get both dense + sparse in one call, cache both
            embedding, sparse = await embeddings.aembed_hybrid(query)
            await cache.store_embedding(query, embedding)
            await cache.store_sparse_embedding(query, sparse)
        else:
            embedding = await embeddings.aembed_query(query)
            await cache.store_embedding(query, embedding)

    # Step 2: Check semantic cache with query-type threshold (allowlisted types only)
    cached = None
    if query_type in CACHEABLE_QUERY_TYPES:
        cached = await cache.check_semantic(
            query=query,
            vector=embedding,
            query_type=query_type,
        )

    latency = time.perf_counter() - start

    if cached:
        logger.info("cache_check HIT (%.3fs, type=%s)", latency, query_type)
        lf.update_current_span(
            output={
                "cache_hit": True,
                "embeddings_cache_hit": embeddings_cache_hit,
                "hit_layer": "semantic",
                "duration_ms": round(latency * 1000, 1),
            }
        )
        return {
            "cache_hit": True,
            "cached_response": cached,
            "query_embedding": embedding,
            "response": cached,
            "embeddings_cache_hit": embeddings_cache_hit,
            "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
        }

    logger.info("cache_check MISS (%.3fs, type=%s)", latency, query_type)
    lf.update_current_span(
        output={
            "cache_hit": False,
            "embeddings_cache_hit": embeddings_cache_hit,
            "hit_layer": "none",
            "duration_ms": round(latency * 1000, 1),
        }
    )
    return {
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": embedding,
        "embeddings_cache_hit": embeddings_cache_hit,
        "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
    }


@observe(name="node-cache-store", capture_input=False, capture_output=False)
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
    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )
    user_id = state.get("user_id", 0)

    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "response_length": len(response),
            "search_results_count": state.get("search_results_count", 0),
        }
    )
    start = time.perf_counter()

    # Store in semantic cache if we have both response and embedding (allowlisted types only)
    stored_semantic = False
    if response and embedding:
        if query_type in CACHEABLE_QUERY_TYPES:
            await cache.store_semantic(
                query=query,
                response=response,
                vector=embedding,
                query_type=query_type,
            )
            stored_semantic = True

        # Store conversation messages (single pipeline round-trip)
        await cache.store_conversation_batch(
            user_id=user_id,
            messages=[("user", query), ("assistant", response)],
        )

        logger.info(
            "cache_store: stored=%s conversation (type=%s)",
            "semantic+" if stored_semantic else "",
            query_type,
        )

        # Log pipeline result event (fire-and-forget, never blocks main flow)
        if event_stream is not None:
            latency_stages = state.get("latency_stages", {})
            total_latency = (
                sum(v for v in latency_stages.values() if isinstance(v, int | float))
                if latency_stages
                else 0
            )
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

    latency = time.perf_counter() - start
    stored_conversation = bool(response and embedding)
    lf.update_current_span(
        output={
            "stored": stored_semantic or stored_conversation,
            "stored_semantic": stored_semantic,
            "stored_conversation": stored_conversation,
            "duration_ms": round(latency * 1000, 1),
        }
    )

    return {"response": response}
