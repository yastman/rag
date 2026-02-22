"""Cache check and store nodes for RAG LangGraph pipeline.

cache_check_node: compute embedding, check semantic cache, return cache_hit.
cache_store_node: store response in semantic cache (allowlisted types only).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe
from telegram_bot.services.metrics import PipelineMetrics


logger = logging.getLogger(__name__)

# Only these query types use semantic cache (check + store).
# GENERAL uses a stricter threshold (0.08) to avoid false positives.
CACHEABLE_QUERY_TYPES: frozenset[str] = frozenset({"FAQ", "ENTITY", "STRUCTURED", "GENERAL"})


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
    embedding_error = False
    embedding_error_type: str | None = None
    colbert_query: list[list[float]] | None = None

    _has_hybrid_colbert = callable(
        getattr(embeddings, "aembed_hybrid_with_colbert", None)
    ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)

    if embedding is None:
        try:
            _has_hybrid = callable(
                getattr(embeddings, "aembed_hybrid", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid)

            if _has_hybrid_colbert:
                # 3-way hybrid: dense + sparse + colbert in one call
                embedding, sparse, colbert_query = await embeddings.aembed_hybrid_with_colbert(
                    query
                )
                await cache.store_embedding(query, embedding)
                await cache.store_sparse_embedding(query, sparse)
            elif _has_hybrid:
                # Hybrid: get both dense + sparse in one call, cache both
                embedding, sparse = await embeddings.aembed_hybrid(query)
                await cache.store_embedding(query, embedding)
                await cache.store_sparse_embedding(query, sparse)
            else:
                embedding = await embeddings.aembed_query(query)
                await cache.store_embedding(query, embedding)
        except Exception as exc:
            embedding_error = True
            embedding_error_type = type(exc).__name__
            logger.error("Embedding failed after retries: %s: %s", embedding_error_type, exc)
            latency = time.perf_counter() - start
            lf.update_current_span(
                level="ERROR",
                output={
                    "embedding_error": True,
                    "embedding_error_type": embedding_error_type,
                    "error_message": str(exc)[:200],
                    "duration_ms": round(latency * 1000, 1),
                },
            )
            return {
                "cache_hit": False,
                "cached_response": None,
                "query_embedding": None,
                "embeddings_cache_hit": False,
                "embedding_error": True,
                "embedding_error_type": embedding_error_type,
                "response": "Сервис временно недоступен. Пожалуйста, повторите через минуту.",
                "latency_stages": {
                    **state.get("latency_stages", {}),
                    "cache_check": latency,
                },
            }

    # Compute ColBERT query vectors when embedding was cached but ColBERT not yet computed.
    # ColBERT vectors are per-query token-level and not cached in Redis.
    if colbert_query is None and _has_hybrid_colbert and embedding is not None:
        try:
            _, _, colbert_query = await embeddings.aembed_hybrid_with_colbert(query)
        except Exception:
            logger.debug("ColBERT query encode failed (non-critical), skipping")

    # Step 2: Check semantic cache with query-type threshold (allowlisted types only).
    # Voice path has no user role — agent_role is intentionally omitted so that
    # voice responses are shared across roles within the same cache_scope="rag" bucket.
    cached = None
    if query_type in CACHEABLE_QUERY_TYPES:
        cached = await cache.check_semantic(
            query=query,
            vector=embedding,
            query_type=query_type,
            cache_scope="rag",
        )

    latency = time.perf_counter() - start

    if cached:
        PipelineMetrics.get().inc("cache_hit")
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
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": colbert_query,
            "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
        }

    PipelineMetrics.get().inc("cache_miss")
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
        "embedding_error": embedding_error,
        "embedding_error_type": embedding_error_type,
        "colbert_query": colbert_query,
        "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
    }


@observe(name="node-cache-store", capture_input=False, capture_output=False)
async def cache_store_node(
    state: dict[str, Any],
    *,
    cache: Any,
    event_stream: Any | None = None,
) -> dict[str, Any]:
    """Store response in semantic cache (allowlisted types only).

    Conversation memory is owned by the LangGraph checkpointer — no legacy
    Redis LIST writes here.

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
    user_id = state.get("user_id")

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
            try:
                # Voice path: agent_role intentionally omitted (no role context in graph state).
                await cache.store_semantic(
                    query=query,
                    response=response,
                    vector=embedding,
                    query_type=query_type,
                    cache_scope="rag",
                )
                stored_semantic = True
            except Exception as exc:
                # RedisVLError, RedisSearchError, SchemaValidationError, or any unexpected
                # error from store_semantic must never lose the response (#524).
                logger.warning(
                    "cache_store: semantic store failed, response preserved: %s: %s",
                    type(exc).__name__,
                    exc,
                )

        if stored_semantic:
            logger.info("cache_store: stored=semantic (type=%s)", query_type)

        # Log pipeline result event (fire-and-forget, never blocks main flow)
        if event_stream is not None:
            latency_stages = state.get("latency_stages", {})
            total_latency = (
                sum(v for v in latency_stages.values() if isinstance(v, int | float))
                if latency_stages
                else 0
            )
            try:
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
            except Exception as exc:
                logger.warning(
                    "cache_store: event_stream.log_event failed: %s: %s", type(exc).__name__, exc
                )

    latency = time.perf_counter() - start
    lf.update_current_span(
        output={
            "stored": stored_semantic,
            "stored_semantic": stored_semantic,
            "duration_ms": round(latency * 1000, 1),
        }
    )

    return {"response": response}
