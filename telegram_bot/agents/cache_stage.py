"""Cache stage helpers extracted from rag_pipeline.py.

Contains _cache_check and _cache_store — the semantic cache read/write steps
that bookend the RAG pipeline. Extracted verbatim from rag_pipeline.py (#card_7bf642f21822).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram_bot.services.rag.cache_policy import (
    SEMANTIC_CACHE_SCHEMA_VERSION,
    build_cacheability_decision,
    is_contextual_query,
    maybe_store_semantic_response,
)
from telegram_bot.services.rag.rag_core import (
    CACHEABLE_QUERY_TYPES,
    check_semantic_cache,
    compute_query_embedding,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Cache check
# ---------------------------------------------------------------------------


async def _cache_check(
    query: str,
    query_type: str,
    user_id: int,
    *,
    cache: Any,
    embeddings: Any,
    latency_stages: dict[str, float],
    agent_role: str | None = None,
    pre_computed_embedding: list[float] | None = None,
    pre_computed_sparse: Any = None,
    pre_computed_colbert: list[list[float]] | None = None,
    semantic_cache_already_checked: bool = False,
    semantic_cache_filter_sensitive: bool = False,
    semantic_cache_filter_signature: str | None = None,
) -> dict[str, Any]:
    """Compute embedding and check semantic cache.

    Returns dict with cache_hit, cached_response, query_embedding, sparse_embedding,
    colbert_query, and latency.
    """

    start = time.perf_counter()

    # Try bundle cache first (avoids redundant BGE-M3 calls when full bundle is cached #1493)
    bundle = None
    _has_bundle_cache = callable(getattr(cache, "get_bge_m3_query_bundle", None))
    if _has_bundle_cache and pre_computed_embedding is None:
        try:
            maybe_bundle = await cache.get_bge_m3_query_bundle(query)
            if (
                maybe_bundle is not None
                and hasattr(maybe_bundle, "dense")
                and isinstance(maybe_bundle.dense, list)
            ):
                bundle = maybe_bundle
        except Exception:
            logger.debug("Bundle cache check failed (non-critical), skipping")

    if bundle is not None:
        embedding = bundle.dense
        sparse = bundle.sparse
        colbert_query = bundle.colbert
        embeddings_cache_hit = True
    else:
        # Step 1: Get or compute dense embedding via shared core
        if pre_computed_embedding:
            logger.debug(
                "_cache_check: reusing pre-computed embedding (%d dims)",
                len(pre_computed_embedding),
            )
        try:
            embedding, sparse, colbert_query, embeddings_cache_hit = await compute_query_embedding(
                query,
                cache=cache,
                embeddings=embeddings,
                pre_computed=pre_computed_embedding,
                pre_computed_sparse=pre_computed_sparse,
                pre_computed_colbert=pre_computed_colbert,
            )
        except Exception as exc:
            embedding_error_type = type(exc).__name__
            logger.error("Embedding failed: %s: %s", embedding_error_type, exc)
            latency = time.perf_counter() - start
            return {
                "cache_hit": False,
                "cached_response": None,
                "query_embedding": None,
                "sparse_embedding": None,
                "embeddings_cache_hit": False,
                "embedding_error": True,
                "embedding_error_type": embedding_error_type,
                "error_response": "Сервис временно недоступен. Пожалуйста, повторите через минуту.",
                "colbert_query": None,
                "latency_stages": {**latency_stages, "cache_check": latency},
            }

    # Step 2: Check semantic cache via shared core
    contextual_query = is_contextual_query(query)
    if (
        semantic_cache_already_checked
        or contextual_query
        or (semantic_cache_filter_sensitive and semantic_cache_filter_signature is None)
    ):
        hit, cached = False, None
    else:
        hit, cached = await check_semantic_cache(
            query,
            embedding,
            query_type,
            cache=cache,
            agent_role=agent_role,
            filter_signature=semantic_cache_filter_signature,
        )

    latency = time.perf_counter() - start

    if hit:
        logger.info("cache_check HIT (%.3fs, type=%s)", latency, query_type)
        return {
            "cache_hit": True,
            "cached_response": cached,
            "query_embedding": embedding,
            "sparse_embedding": sparse,
            "embeddings_cache_hit": embeddings_cache_hit,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": None,
            "latency_stages": {**latency_stages, "cache_check": latency},
        }

    # ColBERT query vectors are only needed on semantic miss.
    if colbert_query is None:
        _has_hybrid_colbert = callable(
            getattr(embeddings, "aembed_hybrid_with_colbert", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)
        _has_colbert_only = callable(
            getattr(embeddings, "aembed_colbert_query", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_colbert_query)

        if _has_hybrid_colbert:
            try:
                _, sparse_from_hybrid, colbert_query = await embeddings.aembed_hybrid_with_colbert(
                    query
                )
                if sparse is None and sparse_from_hybrid is not None:
                    sparse = sparse_from_hybrid
                    if not pre_computed_sparse:
                        await cache.store_sparse_embedding(query, sparse_from_hybrid)
                # Store full bundle for future requests (#1493)
                if (
                    _has_bundle_cache
                    and embedding is not None
                    and sparse is not None
                    and colbert_query is not None
                ):
                    try:
                        from telegram_bot.services.rag.bge_m3_query_bundle import (
                            BgeM3QueryVectorBundle,
                        )

                        await cache.store_bge_m3_query_bundle(
                            query,
                            BgeM3QueryVectorBundle(
                                dense=embedding,
                                sparse=sparse,
                                colbert=colbert_query,
                            ),
                        )
                    except Exception:
                        logger.debug("Bundle store failed (non-critical), skipping")
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")
        elif _has_colbert_only:
            try:
                colbert_query = await embeddings.aembed_colbert_query(query)
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")

    logger.info("cache_check MISS (%.3fs, type=%s)", latency, query_type)
    return {
        "cache_hit": False,
        "cached_response": None,
        "query_embedding": embedding,
        "sparse_embedding": sparse,
        "embeddings_cache_hit": embeddings_cache_hit,
        "embedding_error": False,
        "embedding_error_type": None,
        "colbert_query": colbert_query,
        "latency_stages": {**latency_stages, "cache_check": latency},
    }


# ---------------------------------------------------------------------------
# Step 6: Cache store
# ---------------------------------------------------------------------------


async def _cache_store(
    query: str,
    response: str,
    query_embedding: list[float] | None,
    query_type: str,
    user_id: int,
    *,
    cache: Any,
    search_results_count: int = 0,
    latency_stages: dict[str, float],
    agent_role: str | None = None,
) -> dict[str, Any]:
    """Store response in semantic cache (allowlisted types only).

    Returns dict with latency update.
    """
    start = time.perf_counter()

    stored_semantic = False
    if response and query_embedding and query_type in CACHEABLE_QUERY_TYPES:
        # Legacy helper kept as a thin delegate so tests and older callsites do not
        # carry a second cache-policy implementation.
        decision = build_cacheability_decision(
            result={
                "response": response,
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "fallback_used": False,
                "safe_fallback_used": False,
                "llm_provider_model": "",
                "llm_timeout": False,
            },
            query_type=query_type,
            grounding_mode="normal",
            documents=[{"text": response}],
            cache_hit=False,
            contextual=is_contextual_query(query),
            grade_confidence=1.0,
            confidence_threshold=0.0,
            schema_version=SEMANTIC_CACHE_SCHEMA_VERSION,
        )
        try:
            stored_semantic = await maybe_store_semantic_response(
                cache=cache,
                query=query,
                response=response,
                vector=query_embedding,
                query_type=query_type,
                cache_scope="rag",
                decision=decision,
                agent_role=agent_role,
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

    latency = time.perf_counter() - start

    return {
        "stored_semantic": stored_semantic,
        "latency_stages": {**latency_stages, "cache_store": latency},
    }
