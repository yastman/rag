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

from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
from telegram_bot.observability import get_client, observe
from telegram_bot.services.cache_policy import (
    SEMANTIC_CACHE_SCHEMA_VERSION,
    build_cacheability_decision,
    is_contextual_query,
    maybe_store_semantic_response,
    resolve_semantic_cache_signature,
)
from telegram_bot.services.metrics import PipelineMetrics
from telegram_bot.services.query_filter_signal import detect_filter_sensitive_query
from telegram_bot.services.rag_core import (
    CACHEABLE_QUERY_TYPES,
    check_semantic_cache,
    compute_query_embedding,
)


logger = logging.getLogger(__name__)


def _resolve_graph_filter_signature(state: dict[str, Any], query: str) -> tuple[bool, str | None]:
    filter_sensitive = detect_filter_sensitive_query(query).is_filter_sensitive
    filter_signature = resolve_semantic_cache_signature(
        filters=state.get("filters"),
        explicit_signature=state.get("semantic_cache_filter_signature"),
    )
    return filter_sensitive, filter_signature


@observe(name="node-cache-check", capture_input=False, capture_output=False)
async def cache_check_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """Check semantic cache. Compute embedding if not cached.

    Args:
        state: RAGState dict
        runtime: LangGraph Runtime with GraphContext (cache, embeddings)

    Returns:
        State update with cache_hit, cached_response, query_embedding
    """
    cache: Any = runtime.context["cache"]
    embeddings: Any = runtime.context["embeddings"]
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

    # Step 1: Get or compute dense embedding via shared core.
    # Voice path has no pre-computed vectors — no pre_computed args passed.
    try:
        embedding, _sparse, colbert_query, embeddings_cache_hit = await compute_query_embedding(
            query, cache=cache, embeddings=embeddings
        )
    except Exception as exc:
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

    # Step 2: Check semantic cache via shared core.
    # Voice path has no user role — agent_role omitted so voice responses are
    # shared across roles within the same cache_scope="rag" bucket.
    filter_sensitive, filter_signature = _resolve_graph_filter_signature(state, query)
    contextual_query = is_contextual_query(query)
    if contextual_query or (filter_sensitive and filter_signature is None):
        hit, cached = False, None
    else:
        hit, cached = await check_semantic_cache(
            query,
            embedding,
            query_type,
            cache=cache,
            filter_signature=filter_signature,
        )

    latency = time.perf_counter() - start

    if hit:
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
            "colbert_query": None,
            "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
        }

    # ColBERT vectors are only needed after semantic miss.
    if colbert_query is None:
        _has_hybrid_colbert = callable(
            getattr(embeddings, "aembed_hybrid_with_colbert", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)
        _has_colbert_only = callable(
            getattr(embeddings, "aembed_colbert_query", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_colbert_query)

        if _has_hybrid_colbert:
            try:
                _, sparse, colbert_query = await embeddings.aembed_hybrid_with_colbert(query)
                await cache.store_sparse_embedding(query, sparse)
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")
        elif _has_colbert_only:
            try:
                colbert_query = await embeddings.aembed_colbert_query(query)
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")

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
        "embedding_error": False,
        "embedding_error_type": None,
        "colbert_query": colbert_query,
        "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
    }


@observe(name="node-cache-store", capture_input=False, capture_output=False)
async def cache_store_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """Store response in semantic cache (allowlisted types only).

    Conversation memory is owned by the LangGraph checkpointer — no legacy
    Redis LIST writes here.

    Args:
        state: RAGState dict (must have response, query_embedding, query_type)
        runtime: LangGraph Runtime with GraphContext (cache, event_stream)

    Returns:
        State update (pass-through response)
    """
    cache: Any = runtime.context["cache"]
    event_stream: Any | None = runtime.context.get("event_stream")
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

    # Store in semantic cache if we have both response and embedding.
    stored_semantic = False
    filter_sensitive, filter_signature = _resolve_graph_filter_signature(state, query)
    if (
        response
        and embedding
        and query_type in CACHEABLE_QUERY_TYPES
        and not (filter_sensitive and filter_signature is None)
    ):
        decision = build_cacheability_decision(
            result=state,
            query_type=query_type,
            grounding_mode=str(state.get("grounding_mode", "normal") or "normal"),
            documents=state.get("documents", []),
            cache_hit=bool(state.get("cache_hit", False)),
            contextual=is_contextual_query(query),
            grade_confidence=float(state.get("grade_confidence", 0.0) or 0.0),
            confidence_threshold=0.0,
            schema_version=SEMANTIC_CACHE_SCHEMA_VERSION,
        )
        try:
            # Voice path: agent_role intentionally omitted (no role context in graph state).
            stored_semantic = await maybe_store_semantic_response(
                cache=cache,
                query=query,
                response=response,
                vector=embedding,
                query_type=query_type,
                cache_scope="rag",
                decision=decision,
                filter_signature=filter_signature,
            )
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
