# SPDX-License-Identifier: MIT
"""Hybrid retrieval pipeline stage helpers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.runtime.retrieval import RetrievalService, VectorRetrievalRequest
from src.runtime.services.metrics import record_pipeline_event


logger = logging.getLogger(__name__)

_HARD_EVIDENCE_CONSTRAINTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("castle", ("замок", "castle", "chateau"), ("замок", "castle", "chateau")),
    ("airport", ("аэропорт", "airport"), ("аэропорт", "airport")),
    ("helipad", ("вертол", "helipad", "helicopter"), ("вертол", "helipad", "helicopter")),
)


def _bge_m3_query_bundle_cls() -> Any:
    from src.services.bge_m3_query_bundle import BgeM3QueryVectorBundle

    return BgeM3QueryVectorBundle


def _new_query_preprocessor() -> Any:
    from src.runtime.services.query_preprocessor import QueryPreprocessor

    return QueryPreprocessor()


@dataclass(frozen=True)
class _RetrievalFilterPlan:
    active_filters: dict[str, Any] | None
    relaxed_filters: dict[str, Any] | None
    base_filters: dict[str, Any] | None
    initial_filters: dict[str, Any] | None
    final_filters: dict[str, Any] | None
    prefer_faq_doc_type: bool
    dense_weight: float
    sparse_weight: float


@dataclass
class _RetrievalOutcome:
    results: list[dict[str, Any]]
    search_meta: dict[str, Any]
    colbert_search_used: bool
    final_filters: dict[str, Any] | None
    initial_results_count: int
    qdrant_search_attempts: int
    retrieval_relaxed_from_topic_filter: bool
    retrieval_relax_stage: str | None


def _find_missing_evidence_constraints(
    query: str,
    documents: list[dict[str, Any]],
) -> list[str]:
    """Return hard query constraints that have no evidence in retrieved docs."""
    normalized_query = query.lower()
    evidence_text = "\n".join(_document_evidence_text(doc) for doc in documents).lower()
    missing: list[str] = []
    for name, query_terms, evidence_terms in _HARD_EVIDENCE_CONSTRAINTS:
        if any(term in normalized_query for term in query_terms) and not any(
            term in evidence_text for term in evidence_terms
        ):
            missing.append(name)
    return missing


def _document_evidence_text(document: dict[str, Any]) -> str:
    parts = [str(document.get("text", "")), str(document.get("content", ""))]
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(value) for value in metadata.values())
    return "\n".join(parts)


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
    colbert_used = bool(colbert_query and has_colbert_search)
    retrieval = RetrievalService(qdrant=qdrant)
    result = await retrieval.retrieve_vectors(
        VectorRetrievalRequest(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=filters,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            top_k=top_k,
            return_meta=True,
        )
    )

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


async def _load_cached_query_bundle(cache: Any, query: str) -> Any | None:
    """Return a cached BGE-M3 query bundle if the cache exposes one, else None."""
    if not callable(getattr(cache, "get_bge_m3_query_bundle", None)):
        return None
    try:
        maybe_bundle = await cache.get_bge_m3_query_bundle(query)
    except Exception:
        logger.debug("Bundle cache check failed (non-critical), skipping")
        return None
    if (
        maybe_bundle is not None
        and hasattr(maybe_bundle, "dense")
        and isinstance(maybe_bundle.dense, list)
    ):
        return maybe_bundle
    return None


async def _embed_and_cache_query_vectors(
    query: str,
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
) -> tuple[list[float] | None, Any, list[list[float]] | None]:
    """Embed (and cache) dense/sparse/colbert vectors for a rewritten query.

    Preserves the original fallback ordering exactly:
    embedding-cache -> sparse-cache -> aembed_hybrid_with_colbert ->
    aembed_hybrid -> dense+sparse gather.
    """
    dense_vector: list[float] | None = None
    sparse_vector: Any = None
    colbert_query: list[list[float]] | None = None
    _has_bundle_cache = callable(getattr(cache, "get_bge_m3_query_bundle", None))

    dense_vector = await cache.get_embedding(query)
    if dense_vector is not None:
        return dense_vector, sparse_vector, colbert_query

    sparse_cached = await cache.get_sparse_embedding(query)
    if sparse_cached is not None:
        dense_vector = await embeddings.aembed_query(query)
        await cache.store_embedding(query, dense_vector)
        return dense_vector, sparse_cached, colbert_query

    if callable(
        getattr(embeddings, "aembed_hybrid_with_colbert", None)
    ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert):
        dense_vector, sparse_vector, colbert_query = await embeddings.aembed_hybrid_with_colbert(
            query
        )
        await cache.store_embedding(query, dense_vector)
        await cache.store_sparse_embedding(query, sparse_vector)
        if (
            _has_bundle_cache
            and dense_vector is not None
            and sparse_vector is not None
            and colbert_query is not None
        ):
            try:
                bundle_cls = _bge_m3_query_bundle_cls()
                await cache.store_bge_m3_query_bundle(
                    query,
                    bundle_cls(dense=dense_vector, sparse=sparse_vector, colbert=colbert_query),
                )
            except Exception:
                logger.debug("Bundle store failed (non-critical), skipping")
        return dense_vector, sparse_vector, colbert_query

    if callable(getattr(embeddings, "aembed_hybrid", None)) and asyncio.iscoroutinefunction(
        embeddings.aembed_hybrid
    ):
        dense_vector, sparse_vector = await embeddings.aembed_hybrid(query)
        await cache.store_embedding(query, dense_vector)
        await cache.store_sparse_embedding(query, sparse_vector)
        return dense_vector, sparse_vector, colbert_query

    async def _get_dense() -> list[float]:
        vec: list[float] = await embeddings.aembed_query(query)
        await cache.store_embedding(query, vec)
        return vec

    async def _get_sparse() -> Any:
        vec = await sparse_embeddings.aembed_query(query)
        await cache.store_sparse_embedding(query, vec)
        return vec

    dense_vector, sparse_vector = await asyncio.gather(_get_dense(), _get_sparse())
    return dense_vector, sparse_vector, colbert_query


async def _resolve_query_vectors(
    query: str,
    dense_vector: list[float] | None,
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    *,
    cache: Any,
    embeddings: Any | None,
    sparse_embeddings: Any,
) -> tuple[list[float] | None, Any, list[list[float]] | None]:
    """Resolve dense/sparse/colbert vectors after a query rewrite.

    No-op when dense_vector is already present or embeddings is None.
    """
    if dense_vector is not None or embeddings is None:
        return dense_vector, sparse_vector, colbert_query

    bundle = await _load_cached_query_bundle(cache, query)
    if bundle is not None:
        return bundle.dense, bundle.sparse, bundle.colbert

    return await _embed_and_cache_query_vectors(
        query, cache=cache, embeddings=embeddings, sparse_embeddings=sparse_embeddings
    )


def _compute_retrieval_filters(
    query: str,
    filters: dict[str, Any] | None,
    topic_hint: str | None,
) -> _RetrievalFilterPlan:
    """Build the filter variants and RRF weights used by hybrid retrieval."""
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

    dense_weight, sparse_weight = _new_query_preprocessor().get_rrf_weights(query)

    if prefer_faq_doc_type and topic_hint:
        active_filters = dict(topic_filters)
        active_filters["doc_type"] = "faq"
        relaxed_filters = dict(topic_filters) if topic_filters else None
        initial_filters = dict(active_filters)
        final_filters = dict(active_filters)

    return _RetrievalFilterPlan(
        active_filters=active_filters,
        relaxed_filters=relaxed_filters,
        base_filters=base_filters,
        initial_filters=initial_filters,
        final_filters=final_filters,
        prefer_faq_doc_type=prefer_faq_doc_type,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )


async def _ensure_sparse_vector(
    query: str,
    sparse_vector: Any,
    *,
    cache: Any,
    sparse_embeddings: Any,
) -> Any:
    """Resolve the sparse vector after a confirmed search-cache miss."""
    if sparse_vector is not None:
        return sparse_vector
    sparse_vector = await cache.get_sparse_embedding(query)
    if sparse_vector is None:
        sparse_vector = await sparse_embeddings.aembed_query(query)
        await cache.store_sparse_embedding(query, sparse_vector)
    return sparse_vector


async def _retrieve_with_relaxation(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    plan: _RetrievalFilterPlan,
    top_k: int,
) -> _RetrievalOutcome:
    """Run initial retrieval and up to two topic-filter relaxation stages."""
    active_filters = plan.active_filters
    relaxed_filters = plan.relaxed_filters
    base_filters = plan.base_filters
    dense_weight, sparse_weight = plan.dense_weight, plan.sparse_weight

    colbert_search_used = False
    qdrant_search_attempts = 0
    retrieval_relaxed_from_topic_filter = False
    retrieval_relax_stage: str | None = None

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
    initial_results_count = len(results)
    final_filters = dict(active_filters) if isinstance(active_filters, dict) else None

    if active_filters and len(results) < 3 and active_filters != relaxed_filters:
        record_pipeline_event("topic_filter_fallback")
        retrieval_relaxed_from_topic_filter = True
        fallback_filters = relaxed_filters if relaxed_filters is not None else None
        if plan.prefer_faq_doc_type:
            retrieval_relax_stage = (
                "topic_and_doc_type_to_topic"
                if fallback_filters is not None
                else "topic_and_doc_type_to_none"
            )
        else:
            retrieval_relax_stage = "topic_to_user_filters" if fallback_filters else "topic_to_none"
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
        retrieval_relax_stage = (
            "topic_to_user_filters" if base_filters is not None else "topic_to_none"
        )
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

    return _RetrievalOutcome(
        results=results,
        search_meta=search_meta,
        colbert_search_used=colbert_search_used,
        final_filters=final_filters,
        initial_results_count=initial_results_count,
        qdrant_search_attempts=qdrant_search_attempts,
        retrieval_relaxed_from_topic_filter=retrieval_relaxed_from_topic_filter,
        retrieval_relax_stage=retrieval_relax_stage,
    )


async def _expand_small_to_big(
    final_docs: list[dict[str, Any]],
    *,
    qdrant: Any,
    config: Any,
) -> None:
    """Expand final_docs in-place with neighbor chunks via Small-to-Big service.

    Fetches window_before/window_after sibling chunks per doc from the same
    Qdrant document, replaces each doc's ``text`` with expanded context.
    Failures are logged but never crash the pipeline.
    """
    from src.runtime.services.small_to_big import SmallToBigMode, SmallToBigService

    if config.small_to_big_mode == SmallToBigMode.OFF or not final_docs:
        return
    try:
        stb = SmallToBigService(
            client=qdrant.client,
            collection_name=qdrant.collection_name,
            max_expanded_chunks=config.max_expanded_chunks,
            max_context_tokens=config.max_context_tokens,
        )
        expanded = await stb.expand_context(
            chunks=final_docs,
            window_before=config.small_to_big_window_before,
            window_after=config.small_to_big_window_after,
            deduplicate=True,
        )
        if expanded:
            for i, ec in enumerate(expanded):
                if i < len(final_docs):
                    final_docs[i] = {**final_docs[i], "text": ec.expanded_text, "_expanded": True}
            logger.debug("Small-to-big expanded %d chunks", len(expanded))
    except Exception as e:
        logger.warning("Small-to-big expansion failed: %s", e, exc_info=True)


def _assemble_context(
    *,
    query: str,
    original_query: str,
    documents: list[dict[str, Any]],
    latency_stages: dict[str, float],
    cache_hit: bool,
    embeddings_cache_hit: bool,
    search_cache_hit: bool,
    search_results_count: int,
    rerank_applied: bool,
    rerank_cache_hit: bool,
    grade_confidence: float,
    rewrite_count: int,
    query_type: str,
    query_embedding: list[float] | None,
    cache_key_embedding: list[float] | None,
    retrieved_context: list[dict[str, Any]],
    retrieval_backend_error: bool = False,
    retrieval_error_type: str | None = None,
    topic_hint: str | None = None,
    score_gap_confident: bool | None = None,
    missing_evidence_constraints: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble context dict from pipeline results."""
    return {
        "documents": documents,
        "query": query,
        "original_query": original_query,
        "cache_hit": cache_hit,
        "embeddings_cache_hit": embeddings_cache_hit,
        "search_cache_hit": search_cache_hit,
        "search_results_count": search_results_count,
        "rerank_applied": rerank_applied,
        "rerank_cache_hit": rerank_cache_hit,
        "grade_confidence": grade_confidence,
        "rewrite_count": rewrite_count,
        "query_type": query_type,
        "query_embedding": query_embedding,
        "cache_key_embedding": cache_key_embedding,
        "latency_stages": latency_stages,
        "retrieved_context": retrieved_context,
        "retrieval_backend_error": retrieval_backend_error,
        "retrieval_error_type": retrieval_error_type,
        "topic_hint": topic_hint,
        "score_gap_confident": score_gap_confident,
        "missing_evidence_constraints": missing_evidence_constraints or [],
        "embedding_error": False,
        "embedding_error_type": None,
    }
