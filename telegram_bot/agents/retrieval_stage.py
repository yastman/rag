"""Retrieval stage helpers extracted from rag_pipeline.py.

Contains _execute_qdrant_retrieval, _run_initial_retrieval, _run_relaxed_retrieval,
and _hybrid_retrieve — the hybrid RRF/ColBERT search step of the RAG pipeline.
Extracted verbatim from rag_pipeline.py (#card_7bf642f21822).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.runtime.services.rag_core import (
    build_retrieved_context as _build_retrieved_context,
)
from telegram_bot.services.metrics import record_pipeline_event
from telegram_bot.services.rag.query_preprocessor import QueryPreprocessor


logger = logging.getLogger(__name__)

_QUERY_PREPROCESSOR = QueryPreprocessor()


async def _execute_qdrant_retrieval(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    filters: dict[str, str] | None,
    top_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    has_colbert_search = callable(getattr(qdrant, "hybrid_search_rrf_colbert", None))
    if colbert_query and has_colbert_search:
        result = await qdrant.hybrid_search_rrf_colbert(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=filters,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            top_k=top_k,
            return_meta=True,
        )
        colbert_used = True
    else:
        result = await qdrant.hybrid_search_rrf(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            filters=filters,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            top_k=top_k,
            return_meta=True,
        )
        colbert_used = False

    if isinstance(result, tuple) and len(result) == 2:
        results, search_meta = result
    else:
        results = result
        search_meta = {"backend_error": False, "error_type": None, "error_message": None}
    return results, search_meta, colbert_used


async def _run_initial_retrieval(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    filters: dict[str, str] | None,
    top_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    return await _execute_qdrant_retrieval(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        filters=filters,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )


async def _run_relaxed_retrieval(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    filters: dict[str, str] | None,
    top_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    return await _execute_qdrant_retrieval(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        filters=filters,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )


# ---------------------------------------------------------------------------
# Step 2: Hybrid retrieve
# ---------------------------------------------------------------------------


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

    dense_vector = query_embedding
    # Initialize with pre-computed sparse from _cache_check to avoid redundant BGE-M3 call (#571)
    sparse_vector: Any = sparse_embedding

    # After rewrite, query_embedding is None — re-embed the rewritten query
    if dense_vector is None and embeddings is not None:
        # Check bundle cache first (avoids redundant BGE-M3 calls #1493)
        _has_bundle_cache = callable(getattr(cache, "get_bge_m3_query_bundle", None))
        bundle = None
        if _has_bundle_cache:
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
            dense_vector = bundle.dense
            sparse_vector = bundle.sparse
            colbert_query = bundle.colbert
        else:
            dense_vector = await cache.get_embedding(query)
            if dense_vector is None:
                sparse_cached = await cache.get_sparse_embedding(query)
                if sparse_cached is not None:
                    dense_vector = await embeddings.aembed_query(query)
                    await cache.store_embedding(query, dense_vector)
                    sparse_vector = sparse_cached
                elif callable(
                    getattr(embeddings, "aembed_hybrid_with_colbert", None)
                ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert):
                    (
                        dense_vector,
                        sparse_vector,
                        colbert_query,
                    ) = await embeddings.aembed_hybrid_with_colbert(query)
                    await cache.store_embedding(query, dense_vector)
                    await cache.store_sparse_embedding(query, sparse_vector)
                    # Store full bundle for future requests (#1493)
                    if (
                        _has_bundle_cache
                        and dense_vector is not None
                        and sparse_vector is not None
                        and colbert_query is not None
                    ):
                        try:
                            from src.services.bge_m3_query_bundle import (
                                BgeM3QueryVectorBundle,
                            )

                            await cache.store_bge_m3_query_bundle(
                                query,
                                BgeM3QueryVectorBundle(
                                    dense=dense_vector,
                                    sparse=sparse_vector,
                                    colbert=colbert_query,
                                ),
                            )
                        except Exception:
                            logger.debug("Bundle store failed (non-critical), skipping")
                elif callable(
                    getattr(embeddings, "aembed_hybrid", None)
                ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid):
                    dense_vector, sparse_vector = await embeddings.aembed_hybrid(query)
                    await cache.store_embedding(query, dense_vector)
                    await cache.store_sparse_embedding(query, sparse_vector)
                else:

                    async def _get_dense() -> list[float]:
                        vec: list[float] = await embeddings.aembed_query(query)
                        await cache.store_embedding(query, vec)
                        return vec

                    async def _get_sparse() -> Any:
                        vec = await sparse_embeddings.aembed_query(query)
                        await cache.store_sparse_embedding(query, vec)
                        return vec

                    dense_vector, sparse_vector = await asyncio.gather(_get_dense(), _get_sparse())

    if not dense_vector:
        dense_vector = []

    # Step 1: Compute retrieval filters before touching the search cache.
    colbert_search_used = False
    normalized_query = query.strip().lower()
    query_word_count = len(normalized_query.split()) if normalized_query else 0
    prefer_faq_doc_type = topic_hint == "finance" and 0 < query_word_count <= 2
    base_filters = dict(filters) if isinstance(filters, dict) and filters else None
    topic_filters = dict(base_filters or {})
    if topic_hint:
        topic_filters["topic"] = topic_hint

    active_filters = dict(topic_filters) if topic_filters else None
    relaxed_filters = dict(base_filters) if base_filters else None
    initial_filters = dict(active_filters) if isinstance(active_filters, dict) else None
    final_filters = dict(active_filters) if isinstance(active_filters, dict) else None
    retrieval_relaxed_from_topic_filter = False
    qdrant_search_attempts = 0
    dense_weight, sparse_weight = _QUERY_PREPROCESSOR.get_rrf_weights(query)
    if prefer_faq_doc_type and topic_hint:
        active_filters = dict(topic_filters)
        active_filters["doc_type"] = "faq"
        relaxed_filters = dict(topic_filters) if topic_filters else None
        initial_filters = dict(active_filters)
        final_filters = dict(active_filters)

    start = time.perf_counter()

    # Step 2: Check search cache
    cached_results = await cache.get_search_results(dense_vector, initial_filters)
    if cached_results is not None:
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

    # Step 3: Get sparse embedding only after a confirmed search-cache miss.
    if sparse_vector is None:
        sparse_vector = await cache.get_sparse_embedding(query)
        if sparse_vector is None:
            sparse_vector = await sparse_embeddings.aembed_query(query)
            await cache.store_sparse_embedding(query, sparse_vector)

    # Step 4: Hybrid search via Qdrant SDK (RRF fusion or ColBERT server-side rerank)
    if colbert_query and callable(getattr(qdrant, "hybrid_search_rrf_colbert", None)):
        record_pipeline_event("colbert_rerank_attempted")
    results, search_meta, colbert_used = await _run_initial_retrieval(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        filters=active_filters,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )
    colbert_search_used = colbert_search_used or colbert_used
    qdrant_search_attempts += 1

    if active_filters and len(results) < 3 and active_filters != relaxed_filters:
        record_pipeline_event("topic_filter_fallback")
        retrieval_relaxed_from_topic_filter = True
        fallback_filters = relaxed_filters if relaxed_filters is not None else None
        results, search_meta, colbert_used = await _run_relaxed_retrieval(
            qdrant=qdrant,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=fallback_filters,
            top_k=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
        )
        colbert_search_used = colbert_search_used or colbert_used
        qdrant_search_attempts += 1
        final_filters = dict(fallback_filters) if isinstance(fallback_filters, dict) else None

    if relaxed_filters is not None and len(results) < 3 and final_filters != base_filters:
        results, search_meta, colbert_used = await _run_relaxed_retrieval(
            qdrant=qdrant,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=base_filters,
            top_k=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
        )
        colbert_search_used = colbert_search_used or colbert_used
        qdrant_search_attempts += 1
        final_filters = dict(base_filters) if isinstance(base_filters, dict) else None

    if not results:
        record_pipeline_event("retrieval_zero_docs")

    # Step 5: Cache results
    if results and not search_meta.get("backend_error", False):
        stored_filters: list[dict[str, Any] | None] = []
        cache_targets = [final_filters] if final_filters != initial_filters else [initial_filters]
        for cache_filters in cache_targets:
            normalized_filters = dict(cache_filters) if isinstance(cache_filters, dict) else None
            if normalized_filters in stored_filters:
                continue
            await cache.store_search_results(dense_vector, normalized_filters, results)
            stored_filters.append(normalized_filters)

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
