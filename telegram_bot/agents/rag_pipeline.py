"""RAG pipeline — async functions replacing 11-node LangGraph graph (#442).

Pipeline returns CONTEXT (documents, scores, latency_stages).
Agent generates ANSWER from that context.

Steps:
  1. _cache_check    — compute embedding, check semantic cache
  2. _hybrid_retrieve — hybrid RRF search via Qdrant
  3. _grade_documents — score-based relevance grading
  4. _rerank          — ColBERT reranking or score-sort fallback
  5. _rewrite_query   — LLM query reformulation (loop guard)
  6. _cache_store     — store response in semantic cache

Orchestrator: rag_pipeline() wires steps with rewrite loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

from src.retrieval.topic_classifier import detect_score_gap, get_query_topic_hint
from telegram_bot.observability import get_client, observe
from telegram_bot.pipelines.state_contract import PreAgentStateContract
from telegram_bot.services.query_preprocessor import expand_short_query
from telegram_bot.services.rag_core import (
    CACHEABLE_QUERY_TYPES,
    check_semantic_cache,
    compute_query_embedding,
    perform_rerank,
    rewrite_query_via_llm,
)
from telegram_bot.services.rag_core import (
    build_retrieved_context as _build_retrieved_context,
)


logger = logging.getLogger(__name__)

# top_k=3 for reranking. Saves ~20ms vs top_k=5 while capturing most relevant docs via ColBERT semantic similarity.
_DEFAULT_RERANK_TOP_K = 3


async def _execute_qdrant_retrieval(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    filters: dict[str, str] | None,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    has_colbert_search = callable(getattr(qdrant, "hybrid_search_rrf_colbert", None))
    if colbert_query and has_colbert_search:
        result = await qdrant.hybrid_search_rrf_colbert(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=filters,
            top_k=top_k,
            return_meta=True,
        )
        colbert_used = True
    else:
        result = await qdrant.hybrid_search_rrf(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            filters=filters,
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


@observe(name="retrieval.initial", capture_input=False, capture_output=False)
async def _run_initial_retrieval(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    filters: dict[str, str] | None,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    return await _execute_qdrant_retrieval(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        filters=filters,
        top_k=top_k,
    )


@observe(name="retrieval.relax", capture_input=False, capture_output=False)
async def _run_relaxed_retrieval(
    *,
    qdrant: Any,
    dense_vector: list[float],
    sparse_vector: Any,
    colbert_query: list[list[float]] | None,
    filters: dict[str, str] | None,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    return await _execute_qdrant_retrieval(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        filters=filters,
        top_k=top_k,
    )


# ---------------------------------------------------------------------------
# Step 1: Cache check
# ---------------------------------------------------------------------------


@observe(name="cache-check", capture_input=False, capture_output=False)
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
) -> dict[str, Any]:
    """Compute embedding and check semantic cache.

    Returns dict with cache_hit, cached_response, query_embedding, sparse_embedding,
    colbert_query, and latency.
    """
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

    # Step 1: Get or compute dense embedding via shared core
    if pre_computed_embedding:
        logger.debug(
            "_cache_check: reusing pre-computed embedding (%d dims)", len(pre_computed_embedding)
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
            "sparse_embedding": None,
            "embeddings_cache_hit": False,
            "embedding_error": True,
            "embedding_error_type": embedding_error_type,
            "error_response": "Сервис временно недоступен. Пожалуйста, повторите через минуту.",
            "colbert_query": None,
            "latency_stages": {**latency_stages, "cache_check": latency},
        }

    # Step 2: Check semantic cache via shared core
    hit, cached = await check_semantic_cache(
        query, embedding, query_type, cache=cache, agent_role=agent_role
    )

    latency = time.perf_counter() - start

    if hit:
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
            "sparse_embedding": sparse,
            "embeddings_cache_hit": embeddings_cache_hit,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": None,
            "latency_stages": {**latency_stages, "cache_check": latency},
        }

    # ColBERT query vectors are only needed on semantic miss.
    if colbert_query is None:
        _has_colbert_only = callable(
            getattr(embeddings, "aembed_colbert_query", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_colbert_query)
        _has_hybrid_colbert = callable(
            getattr(embeddings, "aembed_hybrid_with_colbert", None)
        ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid_with_colbert)

        if _has_colbert_only:
            try:
                colbert_query = await embeddings.aembed_colbert_query(query)
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")
        elif _has_hybrid_colbert:
            try:
                _, sparse_from_hybrid, colbert_query = await embeddings.aembed_hybrid_with_colbert(
                    query
                )
                if sparse is None and sparse_from_hybrid is not None:
                    sparse = sparse_from_hybrid
                    if not pre_computed_sparse:
                        await cache.store_sparse_embedding(query, sparse_from_hybrid)
            except Exception:
                logger.debug("ColBERT query encode failed (non-critical), skipping")

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
        "sparse_embedding": sparse,
        "embeddings_cache_hit": embeddings_cache_hit,
        "embedding_error": False,
        "embedding_error_type": None,
        "colbert_query": colbert_query,
        "latency_stages": {**latency_stages, "cache_check": latency},
    }


# ---------------------------------------------------------------------------
# Step 2: Hybrid retrieve
# ---------------------------------------------------------------------------


@observe(name="hybrid-retrieve", capture_input=False, capture_output=False)
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
    topic_hint: str | None = None,
    top_k: int = 20,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Retrieve documents via hybrid RRF search with caching.

    Returns dict with documents, search_results_count, sparse_embedding, and latency.
    """
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "top_k": top_k,
            "topic_hint": topic_hint,
        }
    )

    dense_vector = query_embedding
    # Initialize with pre-computed sparse from _cache_check to avoid redundant BGE-M3 call (#571)
    sparse_vector: Any = sparse_embedding

    # After rewrite, query_embedding is None — re-embed the rewritten query
    if dense_vector is None and embeddings is not None:
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

    start = time.perf_counter()

    # Step 1: Check search cache
    cached_results = await cache.get_search_results(dense_vector)
    if cached_results is not None:
        latency = time.perf_counter() - start
        logger.info("retrieve HIT search cache (%.3fs, %d docs)", latency, len(cached_results))
        cached_ctx = _build_retrieved_context(cached_results)
        lf.update_current_span(
            output={
                "results_count": len(cached_results),
                "search_cache_hit": True,
                "duration_ms": round(latency * 1000, 1),
                "eval_query": query[:2000],
                "eval_docs": "\n\n".join(
                    f"[{d.get('score', 0):.2f}] {str(d.get('content', ''))[:500]}"
                    for d in cached_ctx
                ),
            }
        )
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
        }

    # Step 2: Get sparse embedding (cached or compute)
    if sparse_vector is None:
        sparse_vector = await cache.get_sparse_embedding(query)
        if sparse_vector is None:
            sparse_vector = await sparse_embeddings.aembed_query(query)
            await cache.store_sparse_embedding(query, sparse_vector)

    # Step 3: Hybrid search via Qdrant SDK (RRF fusion or ColBERT server-side rerank)
    colbert_search_used = False
    normalized_query = query.strip().lower()
    query_word_count = len(normalized_query.split()) if normalized_query else 0
    prefer_faq_doc_type = topic_hint == "finance" and 0 < query_word_count <= 2
    filters = {"topic": topic_hint} if topic_hint else None
    relaxed_filters: dict[str, str] | None = None
    initial_filters = dict(filters) if isinstance(filters, dict) else None
    final_filters = dict(filters) if isinstance(filters, dict) else None
    qdrant_search_attempts = 0
    retrieval_relaxed_from_topic_filter = False
    if prefer_faq_doc_type and topic_hint:
        filters = {"topic": topic_hint, "doc_type": "faq"}
        relaxed_filters = {"topic": topic_hint}
        initial_filters = dict(filters)
        final_filters = dict(filters)

    if colbert_query and callable(getattr(qdrant, "hybrid_search_rrf_colbert", None)):
        logger.info("metric", extra={"metric_name": "colbert_rerank_attempted", "value": 1})
    results, search_meta, colbert_used = await _run_initial_retrieval(
        qdrant=qdrant,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        filters=filters,
        top_k=top_k,
    )
    colbert_search_used = colbert_search_used or colbert_used
    qdrant_search_attempts += 1

    if filters and len(results) < 3:
        logger.info(
            "metric",
            extra={"metric_name": "topic_filter_fallback", "value": 1},
        )
        retrieval_relaxed_from_topic_filter = True
        fallback_filters = relaxed_filters if relaxed_filters is not None else None
        results, search_meta, colbert_used = await _run_relaxed_retrieval(
            qdrant=qdrant,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=fallback_filters,
            top_k=top_k,
        )
        colbert_search_used = colbert_search_used or colbert_used
        qdrant_search_attempts += 1
        final_filters = dict(fallback_filters) if isinstance(fallback_filters, dict) else None

    if relaxed_filters is not None and len(results) < 3:
        results, search_meta, colbert_used = await _run_relaxed_retrieval(
            qdrant=qdrant,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            filters=None,
            top_k=top_k,
        )
        colbert_search_used = colbert_search_used or colbert_used
        qdrant_search_attempts += 1
        final_filters = None

    if not results:
        logger.info("metric", extra={"metric_name": "retrieval_zero_docs", "value": 1})

    # Step 4: Cache results
    if results and not search_meta.get("backend_error", False):
        await cache.store_search_results(dense_vector, None, results)

    latency = time.perf_counter() - start
    logger.info("retrieve done (%.3fs, %d docs)", latency, len(results))

    scores = [d.get("score", 0) for d in results if isinstance(d, dict)]
    result_ctx = _build_retrieved_context(results)
    lf.update_current_span(
        output={
            "results_count": len(results),
            "top_score": round(scores[0], 4) if scores else None,
            "min_score": round(scores[-1], 4) if scores else None,
            "search_cache_hit": False,
            "retrieval_backend_error": search_meta.get("backend_error", False),
            "retrieval_error_type": search_meta.get("error_type"),
            "qdrant_search_attempts": qdrant_search_attempts,
            "initial_filters": initial_filters,
            "final_filters": final_filters,
            "retrieval_relaxed_from_topic_filter": retrieval_relaxed_from_topic_filter,
            "duration_ms": round(latency * 1000, 1),
            "eval_query": query[:2000],
            "eval_docs": "\n\n".join(
                f"[{d.get('score', 0):.2f}] {str(d.get('content', ''))[:500]}" for d in result_ctx
            ),
        }
    )

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


# ---------------------------------------------------------------------------
# Step 3: Grade documents
# ---------------------------------------------------------------------------


@observe(name="grade-documents")
async def _grade_documents(
    documents: list[dict[str, Any]],
    prev_confidence: float,
    *,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Grade retrieved documents by relevance using score-based heuristic.

    Returns dict with documents_relevant, grade_confidence, skip_rerank, score_improved.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**latency_stages, "grade": elapsed},
        }

    scores = [doc.get("score", 0) for doc in documents if isinstance(doc, dict)]
    if not scores:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no valid scored documents (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**latency_stages, "grade": elapsed},
        }

    top_score = max(scores)
    score_gap = detect_score_gap(sorted(scores, reverse=True))

    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()
    relevant = top_score > config.relevance_threshold_rrf
    skip_rerank = relevant and top_score >= config.skip_rerank_threshold

    delta = top_score - prev_confidence
    score_improved = delta >= config.score_improvement_delta or prev_confidence == 0.0

    elapsed = time.perf_counter() - t0
    logger.info(
        "grade: top_score=%.4f prev=%.4f delta=%.4f improved=%s "
        "threshold=%.3f relevant=%s skip_rerank=%s (%d docs, %.3fs)",
        top_score,
        prev_confidence,
        delta,
        score_improved,
        config.relevance_threshold_rrf,
        relevant,
        skip_rerank,
        len(documents),
        elapsed,
    )
    logger.info(
        "metric",
        extra={"metric_name": "score_gap_confident", "value": 1 if score_gap["confident"] else 0},
    )

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "score_improved": score_improved,
        "score_gap_confident": score_gap["confident"],
        "latency_stages": {**latency_stages, "grade": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 4: Rerank
# ---------------------------------------------------------------------------


@observe(name="rerank")
async def _rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    cache: Any | None = None,
    reranker: Any | None = None,
    top_k: int = _DEFAULT_RERANK_TOP_K,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rerank documents using ColBERT or score-based fallback.

    Returns dict with documents, rerank_applied, rerank_cache_hit, and latency.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        return {
            "documents": [],
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "latency_stages": {**latency_stages, "rerank": elapsed},
        }

    try:
        reranked_docs, rerank_applied, rerank_cache_hit = await perform_rerank(
            query, documents, cache=cache, reranker=reranker, top_k=top_k
        )
        if not rerank_applied:
            # No reranker path: sort and trim here
            reranked_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]
    except Exception as e:
        logger.exception("rerank: ColBERT failed, falling back to score sort")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"ColBERT rerank failed: {str(e)[:200]}",
        )
        reranked_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]
        rerank_applied = False
        rerank_cache_hit = False

    if len(reranked_docs) >= 3:
        top_scores = [float(doc.get("score", 0.0)) for doc in reranked_docs[:3]]
        lead_gap = detect_score_gap(top_scores[:2])
        tail_gap = detect_score_gap(top_scores[1:3])
        if not bool(lead_gap["confident"]) and bool(tail_gap["confident"]):
            reranked_docs = reranked_docs[:2]

    elapsed = time.perf_counter() - t0
    logger.info(
        "rerank: %d → %d docs, applied=%s cache_hit=%s (%.3fs)",
        len(documents),
        len(reranked_docs),
        rerank_applied,
        rerank_cache_hit,
        elapsed,
    )
    return {
        "documents": reranked_docs,
        "rerank_applied": rerank_applied,
        "rerank_cache_hit": rerank_cache_hit,
        "latency_stages": {**latency_stages, "rerank": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 5: Rewrite query
# ---------------------------------------------------------------------------


@observe(name="query-rewrite")
async def _rewrite_query(
    query: str,
    rewrite_count: int,
    *,
    llm: Any | None = None,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rewrite user query for better retrieval.

    Returns dict with rewritten_query, rewrite_count, rewrite_effective, and latency.
    """
    t0 = time.perf_counter()
    topic_hint = get_query_topic_hint(query)
    expanded_query = expand_short_query(
        query,
        topic_hint=topic_hint.value if topic_hint is not None else None,
    )
    if expanded_query != query:
        elapsed = time.perf_counter() - t0
        logger.info(
            "rewrite: deterministic expansion '%s' → '%s' (%.3fs)",
            query,
            expanded_query,
            elapsed,
        )
        return {
            "rewritten_query": expanded_query,
            "rewrite_count": rewrite_count + 1,
            "rewrite_effective": True,
            "rewrite_provider_model": "deterministic_short_query_expansion",
            "latency_stages": {**latency_stages, "rewrite": elapsed},
        }

    try:
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()
        rewritten, effective, rewrite_actual_model = await rewrite_query_via_llm(query, llm=llm)
    except Exception as e:
        logger.exception("rewrite: LLM rewrite failed, keeping original query")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"Rewrite LLM failed: {str(e)[:200]}",
        )
        rewritten = query
        effective = False
        rewrite_actual_model = "fallback"

    elapsed = time.perf_counter() - t0
    logger.info(
        "rewrite: attempt %d, '%.50s' → '%.50s' (%.3fs)",
        rewrite_count + 1,
        query,
        rewritten,
        elapsed,
    )

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count + 1,
        "rewrite_effective": effective,
        "rewrite_provider_model": rewrite_actual_model,
        "latency_stages": {**latency_stages, "rewrite": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 6: Cache store
# ---------------------------------------------------------------------------


@observe(name="cache-store", capture_input=False, capture_output=False)
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
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "response_length": len(response),
            "search_results_count": search_results_count,
        }
    )
    start = time.perf_counter()

    stored_semantic = False
    if response and query_embedding:
        if query_type in CACHEABLE_QUERY_TYPES:
            try:
                await cache.store_semantic(
                    query=query,
                    response=response,
                    vector=query_embedding,
                    query_type=query_type,
                    cache_scope="rag",
                    agent_role=agent_role,
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

    latency = time.perf_counter() - start
    lf.update_current_span(
        output={
            "stored": stored_semantic,
            "stored_semantic": stored_semantic,
            "duration_ms": round(latency * 1000, 1),
        }
    )

    return {
        "stored_semantic": stored_semantic,
        "latency_stages": {**latency_stages, "cache_store": latency},
    }


# ---------------------------------------------------------------------------
# Orchestrator: rag_pipeline()
# ---------------------------------------------------------------------------


@observe(name="rag-pipeline", capture_input=False, capture_output=False)
async def rag_pipeline(
    query: str,
    *,
    user_id: int,
    session_id: str,
    query_type: str = "GENERAL",
    original_query: str = "",
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
    agent_role: str | None = None,
    state_contract: PreAgentStateContract | None = None,
    pre_computed_embedding: list[float] | None = None,
    pre_computed_sparse: Any = None,
    pre_computed_colbert: list[list[float]] | None = None,
    skip_rewrite: bool = False,
) -> dict[str, Any]:
    """Execute RAG pipeline: cache → retrieve → grade → rerank → rewrite loop → cache_store.

    Returns context dict with documents, scores, latency_stages, and pipeline metadata.
    The caller (agent) is responsible for generating the final answer from documents.

    Args:
        query: The (possibly reformulated) query used for retrieval.
        original_query: The original user query before agent reformulation.
            Used as the semantic cache key so repeated user queries hit the cache
            even when the agent reformulates them differently. Falls back to query
            when empty (voice path, direct calls).
    """
    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()

    # cache_key: use original user query for semantic cache so repeated queries hit
    # even when the agent reformulates them. Falls back to query when not provided.
    cache_key = original_query or query

    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "original_query_preview": cache_key[:120] if cache_key != query else None,
            "user_id": user_id,
            "session_id": session_id,
            "query_type": query_type,
        }
    )

    latency_stages: dict[str, float] = {}
    rewrite_count = 0
    rewrite_effective = True
    grade_confidence = 0.0
    current_query = query
    query_embedding: list[float] | None = None
    contract_topic_hint = state_contract.get("topic_hint") if state_contract is not None else None
    topic_hint = contract_topic_hint or get_query_topic_hint(query)
    semantic_cache_already_checked = False

    # Step 1: Cache check (use cache_key = original user query)
    # Pass pre_computed_embedding when caller already computed it (avoids redundant BGE-M3 call).
    if (
        state_contract is not None
        and state_contract.get("cache_checked") is True
        and state_contract.get("cache_hit") is False
        and state_contract.get("embedding_bundle_ready") is True
    ):
        semantic_cache_already_checked = True
        cache_result = {
            "cache_hit": False,
            "cached_response": None,
            "query_embedding": state_contract.get("dense_vector"),
            "sparse_embedding": state_contract.get("sparse_vector"),
            "embeddings_cache_hit": False,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": state_contract.get("colbert_query"),
            "latency_stages": latency_stages,
        }
    else:
        cache_result = await _cache_check(
            cache_key,
            query_type,
            user_id,
            cache=cache,
            embeddings=embeddings,
            latency_stages=latency_stages,
            agent_role=agent_role,
            pre_computed_embedding=pre_computed_embedding,
            pre_computed_sparse=pre_computed_sparse,
            pre_computed_colbert=pre_computed_colbert,
        )
    # Embedding of cache_key — kept separately for _cache_store so rewrites don't overwrite it
    cache_embedding: list[float] | None = cache_result.get("query_embedding")
    cache_sparse: Any = cache_result.get("sparse_embedding")
    latency_stages = cache_result["latency_stages"]
    colbert_query: list[list[float]] | None = cache_result.get("colbert_query")

    if cache_result.get("embedding_error"):
        return {
            "response": cache_result.get("error_response", ""),
            "cache_hit": False,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": False,
            "embedding_error": True,
            "embedding_error_type": cache_result.get("embedding_error_type"),
            "latency_stages": latency_stages,
            "rewrite_count": 0,
            "query_type": query_type,
            "retrieved_context": [],
            "semantic_cache_already_checked": semantic_cache_already_checked,
        }

    if cache_result["cache_hit"]:
        return {
            "response": cache_result["cached_response"],
            "cache_hit": True,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": cache_result["embeddings_cache_hit"],
            "embedding_error": False,
            "embedding_error_type": None,
            "latency_stages": latency_stages,
            "rewrite_count": 0,
            "query_type": query_type,
            "retrieved_context": [],
            "semantic_cache_already_checked": semantic_cache_already_checked,
        }

    # For retrieval, use reformulated query embedding.
    # If cache_key differs from query (agent reformulated), pre-fetch the
    # reformulated query embedding for the FIRST retrieval attempt. This avoids a
    # redundant BGE-M3 call in _hybrid_retrieve on warm requests (#513).
    # Subsequent iterations after _rewrite_query set query_embedding = None and
    # let _hybrid_retrieve handle cache lookup for those new rewritten queries.
    if cache_key != query:
        # Agent reformulated query — all pre-computed embeddings are for original text.
        # Let _hybrid_retrieve do ONE combined aembed_hybrid_with_colbert call (#951).
        query_embedding = None
        colbert_query = None
        query_sparse: Any = None
    else:
        query_embedding = cache_embedding
        query_sparse = cache_sparse  # reuse sparse from _cache_check for this query (#571)

    # Retrieve → grade → (rerank | rewrite loop)
    for _attempt in range(config.max_rewrite_attempts + 1):
        # Step 2: Hybrid retrieve
        retrieve_result = await _hybrid_retrieve(
            current_query,
            query_embedding,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
            embeddings=embeddings,
            colbert_query=colbert_query,
            sparse_embedding=query_sparse,
            topic_hint=topic_hint,
            latency_stages=latency_stages,
        )
        latency_stages = retrieve_result["latency_stages"]
        documents = retrieve_result["documents"]
        query_embedding = retrieve_result.get("query_embedding", query_embedding)
        colbert_query = retrieve_result.get("colbert_query", colbert_query)

        # Step 3: Grade documents
        grade_result = await _grade_documents(
            documents,
            grade_confidence,
            latency_stages=latency_stages,
        )
        latency_stages = grade_result["latency_stages"]
        grade_confidence = grade_result["grade_confidence"]

        if grade_result["documents_relevant"]:
            # Step 4: Rerank (if needed)
            rerank_from_retrieve = retrieve_result.get("rerank_applied", False)
            if grade_result["skip_rerank"] or rerank_from_retrieve:
                # High confidence or server-side ColBERT already applied — skip rerank
                final_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[
                    :_DEFAULT_RERANK_TOP_K
                ]
                rerank_applied = rerank_from_retrieve  # preserve True from ColBERT path
                rerank_cache_hit = False
            else:
                rerank_result = await _rerank(
                    current_query,
                    documents,
                    cache=cache,
                    reranker=reranker,
                    latency_stages=latency_stages,
                )
                latency_stages = rerank_result["latency_stages"]
                final_docs = rerank_result["documents"]
                rerank_applied = rerank_result["rerank_applied"]
                rerank_cache_hit = rerank_result["rerank_cache_hit"]
            final_gap = detect_score_gap(
                [doc.get("score", 0.0) for doc in final_docs if isinstance(doc, dict)]
            )
            final_gap_confident = bool(final_gap["confident"])
            if not final_gap_confident and len(final_docs) > 1:
                final_docs = final_docs[:1]

            result = _assemble_context(
                query=current_query,
                original_query=query,
                documents=final_docs,
                latency_stages=latency_stages,
                cache_hit=False,
                embeddings_cache_hit=cache_result["embeddings_cache_hit"],
                search_cache_hit=retrieve_result.get("search_cache_hit", False),
                search_results_count=retrieve_result["search_results_count"],
                rerank_applied=rerank_applied,
                rerank_cache_hit=rerank_cache_hit,
                grade_confidence=grade_confidence,
                rewrite_count=rewrite_count,
                query_type=query_type,
                query_embedding=query_embedding,
                cache_key_embedding=cache_embedding,
                retrieved_context=retrieve_result.get("retrieved_context", []),
                retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
                retrieval_error_type=retrieve_result.get("retrieval_error_type"),
                topic_hint=topic_hint,
                score_gap_confident=final_gap_confident,
            )
            result["skip_rewrite"] = skip_rewrite
            result["semantic_cache_already_checked"] = semantic_cache_already_checked
            lf.update_current_span(
                output={
                    "cache_hit": False,
                    "documents_count": len(final_docs),
                    "rerank_applied": rerank_applied,
                    "rewrite_count": rewrite_count,
                }
            )
            return result

        # Check if we should rewrite
        can_rewrite = (
            rewrite_count < config.max_rewrite_attempts
            and not skip_rewrite
            and rewrite_effective
            and grade_result.get("score_improved", True)
        )
        if not can_rewrite:
            break

        # Step 5: Rewrite query
        rewrite_result = await _rewrite_query(
            current_query,
            rewrite_count,
            llm=llm,
            latency_stages=latency_stages,
        )
        latency_stages = rewrite_result["latency_stages"]
        current_query = rewrite_result["rewritten_query"]
        rewrite_count = rewrite_result["rewrite_count"]
        rewrite_effective = rewrite_result["rewrite_effective"]
        topic_hint = get_query_topic_hint(current_query)
        query_embedding = None  # Force re-embed on next retrieve
        colbert_query = None  # Force re-encode ColBERT on next retrieve
        query_sparse = None  # Force re-compute sparse on next retrieve (query changed)

    # Fallback: ran out of rewrites, return best docs with rerank
    rerank_from_retrieve = retrieve_result.get("rerank_applied", False)
    if rerank_from_retrieve:
        # Server-side ColBERT already applied — skip separate rerank
        final_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[
            :_DEFAULT_RERANK_TOP_K
        ]
        rerank_applied = True
        rerank_cache_hit = False
    else:
        rerank_result = await _rerank(
            current_query,
            documents,
            cache=cache,
            reranker=reranker,
            latency_stages=latency_stages,
        )
        latency_stages = rerank_result["latency_stages"]
        final_docs = rerank_result["documents"]
        rerank_applied = rerank_result["rerank_applied"]
        rerank_cache_hit = rerank_result["rerank_cache_hit"]
    final_gap = detect_score_gap(
        [doc.get("score", 0.0) for doc in final_docs if isinstance(doc, dict)]
    )
    final_gap_confident = bool(final_gap["confident"])
    if not final_gap_confident and len(final_docs) > 1:
        final_docs = final_docs[:1]

    result = _assemble_context(
        query=current_query,
        original_query=query,
        documents=final_docs,
        latency_stages=latency_stages,
        cache_hit=False,
        embeddings_cache_hit=cache_result["embeddings_cache_hit"],
        search_cache_hit=retrieve_result.get("search_cache_hit", False),
        search_results_count=retrieve_result["search_results_count"],
        rerank_applied=rerank_applied,
        rerank_cache_hit=rerank_cache_hit,
        grade_confidence=grade_confidence,
        rewrite_count=rewrite_count,
        query_type=query_type,
        query_embedding=query_embedding,
        cache_key_embedding=cache_embedding,
        retrieved_context=retrieve_result.get("retrieved_context", []),
        retrieval_backend_error=retrieve_result.get("retrieval_backend_error", False),
        retrieval_error_type=retrieve_result.get("retrieval_error_type"),
        topic_hint=topic_hint,
        score_gap_confident=final_gap_confident,
    )
    result["skip_rewrite"] = skip_rewrite
    result["semantic_cache_already_checked"] = semantic_cache_already_checked
    lf.update_current_span(
        output={
            "cache_hit": False,
            "documents_count": len(final_docs),
            "rerank_applied": rerank_applied,
            "rewrite_count": rewrite_count,
            "fallback": True,
        }
    )
    return result


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
        "embedding_error": False,
        "embedding_error_type": None,
    }
