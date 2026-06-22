# SPDX-License-Identifier: MIT
"""Cache check, search-result cache, and search-cache lookup pipeline stages."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.runtime.pipeline._retrieve import (
    _compute_retrieval_filters,
    _ensure_sparse_vector,
    _resolve_query_vectors,
    _retrieve_with_relaxation,
)
from src.runtime.services.cache_policy import is_contextual_query
from src.runtime.services.metrics import record_pipeline_event
from src.runtime.services.rag_core import check_semantic_cache, compute_query_embedding


logger = logging.getLogger(__name__)


def _bge_m3_query_bundle_cls() -> Any:
    from src.services.bge_m3_query_bundle import BgeM3QueryVectorBundle

    return BgeM3QueryVectorBundle


def _build_retrieved_context(*args: Any, **kwargs: Any) -> Any:
    from src.runtime.services.rag_core import build_retrieved_context

    return build_retrieved_context(*args, **kwargs)


async def _store_search_results(
    *,
    cache: Any,
    dense_vector: list[float],
    results: list[dict[str, Any]],
    search_meta: dict[str, Any],
    initial_filters: dict[str, Any] | None,
    final_filters: dict[str, Any] | None,
    retrieval_config: dict[str, Any],
) -> None:
    """Store retrieval results under the de-duplicated filter targets."""
    if not results or search_meta.get("backend_error", False):
        return
    stored_filters: list[dict[str, Any] | None] = []
    cache_targets = [final_filters] if final_filters != initial_filters else [initial_filters]
    for cache_filters in cache_targets:
        normalized_filters = dict(cache_filters) if isinstance(cache_filters, dict) else None
        if normalized_filters in stored_filters:
            continue
        await cache.store_search_results(
            dense_vector, normalized_filters, results, retrieval_config=retrieval_config
        )
        stored_filters.append(normalized_filters)


async def _lookup_search_cache(
    query: str,
    dense_vector: list[float],
    initial_filters: dict[str, Any] | None,
    *,
    cache: Any,
    colbert_query: list[list[float]] | None,
    top_k: int,
    latency_stages: dict[str, float],
) -> dict[str, Any] | None:
    """Return a cached retrieval payload on hit, else None. Emits span on hit."""
    start = time.perf_counter()
    retrieval_cfg: dict = {"top_k": top_k}
    cached_results = await cache.get_search_results(
        dense_vector, initial_filters, retrieval_config=retrieval_cfg
    )
    if cached_results is None:
        return None

    latency = time.perf_counter() - start
    logger.info("retrieve HIT search cache (%.3fs, %d docs)", latency, len(cached_results))
    cached_ctx = _build_retrieved_context(cached_results)
    return {
        "documents": cached_results,
        "search_results_count": len(cached_results),
        "search_cache_hit": True,
        "query_embedding": dense_vector,
        "latency_stages": {**latency_stages, "retrieve": latency},
        "retrieval_backend_error": False,
        "retrieval_error_type": None,
        "retrieved_context": cached_ctx,
        "rerank_applied": False,
        "colbert_query": colbert_query,
        "initial_filters": initial_filters,
        "final_filters": initial_filters,
    }


async def _resolve_bundle_cache(
    query: str,
    *,
    cache: Any,
    pre_computed_embedding: list[float] | None,
) -> Any:
    """Try to load a full BGE-M3 vector bundle from cache (#1493).

    Returns the bundle on hit, None on miss or when pre_computed_embedding is set
    (pre-computed path skips the bundle lookup entirely).
    """
    if pre_computed_embedding is not None:
        return None
    if not callable(getattr(cache, "get_bge_m3_query_bundle", None)):
        return None
    try:
        maybe = await cache.get_bge_m3_query_bundle(query)
        if maybe is not None and hasattr(maybe, "dense") and isinstance(maybe.dense, list):
            return maybe
    except Exception:
        logger.debug("Bundle cache check failed (non-critical), skipping")
    return None


async def _resolve_embeddings(
    query: str,
    *,
    cache: Any,
    embeddings: Any,
    pre_computed_embedding: list[float] | None,
    pre_computed_sparse: Any,
    pre_computed_colbert: list[list[float]] | None,
) -> tuple[list[float] | None, Any, list[list[float]] | None, bool, str | None]:
    """Compute or retrieve dense+sparse+colbert embeddings.

    Returns (embedding, sparse, colbert_query, embeddings_cache_hit, error_type).
    error_type is non-None when embedding computation failed.
    """
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
        return embedding, sparse, colbert_query, embeddings_cache_hit, None
    except Exception as exc:
        error_type = type(exc).__name__
        logger.error("Embedding failed: %s: %s", error_type, exc)
        return None, None, None, False, error_type


async def _resolve_colbert_on_miss(
    query: str,
    embedding: list[float] | None,
    sparse: Any,
    *,
    cache: Any,
    embeddings: Any,
    pre_computed_sparse: Any,
) -> tuple[list[list[float]] | None, Any]:
    """Compute ColBERT vectors after a semantic-cache miss (lazy, avoids cost on hits).

    Also fills in sparse vectors and stores the full bundle when possible (#1493).
    Returns (colbert_query, sparse) — sparse may be updated if hybrid call provides it.
    """
    _has_hybrid_colbert = callable(
        getattr(embeddings, "aembed_hybrid_with_colbert", None)
    ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)
    _has_colbert_only = callable(
        getattr(embeddings, "aembed_colbert_query", None)
    ) and asyncio.iscoroutinefunction(embeddings.aembed_colbert_query)

    colbert_query: list[list[float]] | None = None

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
            _has_bundle_cache = callable(getattr(cache, "get_bge_m3_query_bundle", None))
            if (
                _has_bundle_cache
                and embedding is not None
                and sparse is not None
                and colbert_query is not None
            ):
                try:
                    bundle_cls = _bge_m3_query_bundle_cls()
                    await cache.store_bge_m3_query_bundle(
                        query,
                        bundle_cls(dense=embedding, sparse=sparse, colbert=colbert_query),
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

    return colbert_query, sparse


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

    # Stage A: Try full bundle cache (avoids redundant BGE-M3 calls #1493)
    bundle = await _resolve_bundle_cache(
        query, cache=cache, pre_computed_embedding=pre_computed_embedding
    )
    if bundle is not None:
        embedding: list[float] | None = bundle.dense
        sparse: Any = bundle.sparse
        colbert_query: list[list[float]] | None = bundle.colbert
        embeddings_cache_hit = True
    else:
        # Stage B: Compute/retrieve dense+sparse embeddings
        (
            embedding,
            sparse,
            colbert_query,
            embeddings_cache_hit,
            error_type,
        ) = await _resolve_embeddings(
            query,
            cache=cache,
            embeddings=embeddings,
            pre_computed_embedding=pre_computed_embedding,
            pre_computed_sparse=pre_computed_sparse,
            pre_computed_colbert=pre_computed_colbert,
        )
        if error_type is not None:
            latency = time.perf_counter() - start
            return {
                "cache_hit": False,
                "cached_response": None,
                "query_embedding": None,
                "sparse_embedding": None,
                "embeddings_cache_hit": False,
                "embedding_error": True,
                "embedding_error_type": error_type,
                "error_response": "Сервис временно недоступен. Пожалуйста, повторите через минуту.",
                "colbert_query": None,
                "latency_stages": {**latency_stages, "cache_check": latency},
            }

    # Stage C: Check semantic cache
    contextual_query = is_contextual_query(query)
    skip_semantic = (
        semantic_cache_already_checked
        or contextual_query
        or (semantic_cache_filter_sensitive and semantic_cache_filter_signature is None)
        or embedding is None
    )
    if skip_semantic:
        hit, cached = False, None
    else:
        assert embedding is not None  # narrowed: error path already returned above
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

    # Stage D: Compute ColBERT vectors on miss (lazy — skipped on cache hits)
    if colbert_query is None:
        colbert_query, sparse = await _resolve_colbert_on_miss(
            query,
            embedding,
            sparse,
            cache=cache,
            embeddings=embeddings,
            pre_computed_sparse=pre_computed_sparse,
        )

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


async def _hybrid_retrieve(
    query: str,
    query_embedding: list[float] | None,
    *,
    cache: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    embeddings: Any | None = None,
    colbert_query: list[list[float]] | None = None,
    sparse_embedding: Any = None,
    filters: dict[str, Any] | None = None,
    topic_hint: str | None = None,
    top_k: int = 20,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Retrieve documents via hybrid RRF search with caching.

    Returns dict with documents, search_results_count, sparse_embedding, and latency.
    """

    dense_vector, sparse_vector, colbert_query = await _resolve_query_vectors(
        query,
        query_embedding,
        sparse_embedding,
        colbert_query,
        cache=cache,
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
    )

    if not dense_vector:
        dense_vector = []

    plan = _compute_retrieval_filters(query, filters, topic_hint)
    initial_filters = plan.initial_filters
    _dense_weight, _sparse_weight = plan.dense_weight, plan.sparse_weight

    start = time.perf_counter()

    _retrieval_cfg: dict = {"top_k": top_k}
    cached_payload = await _lookup_search_cache(
        query,
        dense_vector,
        initial_filters,
        cache=cache,
        colbert_query=colbert_query,
        top_k=top_k,
        latency_stages=latency_stages,
    )
    if cached_payload is not None:
        return cached_payload

    sparse_vector = await _ensure_sparse_vector(
        query, sparse_vector, cache=cache, sparse_embeddings=sparse_embeddings
    )

    outcome = await _retrieve_with_relaxation(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        plan=plan,
        top_k=top_k,
    )
    results = outcome.results
    search_meta = outcome.search_meta
    colbert_search_used = outcome.colbert_search_used
    final_filters = outcome.final_filters
    qdrant_search_attempts = outcome.qdrant_search_attempts
    retrieval_relaxed_from_topic_filter = outcome.retrieval_relaxed_from_topic_filter

    if not results:
        record_pipeline_event("retrieval_zero_docs")

    await _store_search_results(
        cache=cache,
        dense_vector=dense_vector,
        results=results,
        search_meta=search_meta,
        initial_filters=initial_filters,
        final_filters=final_filters,
        retrieval_config=_retrieval_cfg,
    )

    latency = time.perf_counter() - start
    logger.info("retrieve done (%.3fs, %d docs)", latency, len(results))

    result_ctx = _build_retrieved_context(results)

    return {
        "documents": results,
        "search_results_count": len(results),
        "search_cache_hit": False,
        "sparse_embedding": sparse_vector,
        "query_embedding": dense_vector or None,
        "latency_stages": {**latency_stages, "retrieve": latency},
        "retrieval_backend_error": search_meta.get("backend_error", False),
        "retrieval_error_type": search_meta.get("error_type"),
        "retrieved_context": result_ctx,
        "rerank_applied": colbert_search_used,
        "colbert_query": colbert_query,
        "qdrant_search_attempts": qdrant_search_attempts,
        "initial_filters": initial_filters,
        "final_filters": final_filters,
        "retrieval_relaxed_from_topic_filter": retrieval_relaxed_from_topic_filter,
    }
