"""Retrieve node for RAG LangGraph pipeline.

Performs hybrid RRF search via QdrantService with search cache integration.
Uses direct Qdrant SDK (NOT langchain_qdrant) for full control over
prefetch, FusionQuery, and ColBERT reranking.
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
from telegram_bot.services.coverage_mode import cap_results_per_doc, detect_coverage_mode
from telegram_bot.services.metrics import PipelineMetrics
from telegram_bot.services.rag_core import build_retrieved_context as _build_retrieved_context


logger = logging.getLogger(__name__)


def _build_search_cache_profile(
    *,
    needs_coverage: bool,
    use_colbert: bool,
    top_k: int,
) -> dict[str, Any]:
    if needs_coverage:
        return {
            "mode": "coverage",
            "top_k": 10,
            "group_by": "metadata.doc_id",
            "group_size": 2,
            "prefetch_multiplier": 7,
        }
    if use_colbert:
        return {"mode": "colbert", "top_k": top_k}
    return {"mode": "rrf", "top_k": top_k}


def _distinct_doc_count(results: list[dict[str, Any]]) -> int:
    return len(
        {
            str((doc.get("metadata", {}) or {}).get("doc_id") or doc.get("id") or "")
            for doc in results
        }
    )


@observe(name="node-retrieve", capture_input=False, capture_output=False)
async def retrieve_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
    top_k: int = 20,
) -> dict[str, Any]:
    """Retrieve documents via hybrid RRF search with caching.

    Flow:
      1. Check search cache (by embedding prefix + filters)
      2. If miss: get sparse embedding (cached or compute)
      3. Call qdrant.hybrid_search_rrf()
      4. Cache results

    Args:
        state: RAGState dict (needs query_embedding)
        runtime: LangGraph Runtime with GraphContext (cache, embeddings, sparse_embeddings, qdrant)
        top_k: Number of results to retrieve

    Returns:
        State update with documents, search_results_count, sparse_embedding
    """
    cache: Any = runtime.context["cache"]
    sparse_embeddings: Any = runtime.context["sparse_embeddings"]
    qdrant: Any = runtime.context["qdrant"]
    embeddings: Any | None = runtime.context.get("embeddings")
    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )
    coverage_decision = detect_coverage_mode(query)
    needs_coverage = bool(state.get("needs_coverage")) or coverage_decision.needs_coverage
    effective_top_k = 10 if needs_coverage else top_k
    colbert_query = state.get("colbert_query")
    _has_colbert_search = callable(getattr(qdrant, "hybrid_search_rrf_colbert", None))
    search_cache_profile = _build_search_cache_profile(
        needs_coverage=needs_coverage,
        use_colbert=bool(colbert_query and _has_colbert_search),
        top_k=effective_top_k,
    )

    # Curated span metadata (replaces auto-captured full state)
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "query_type": state.get("query_type"),
            "top_k": effective_top_k,
            "needs_coverage": needs_coverage,
            "coverage_reason": coverage_decision.reason,
        }
    )

    dense_vector = state.get("query_embedding")
    sparse_vector: Any = None

    # After rewrite, query_embedding is None — re-embed the rewritten query
    if dense_vector is None and embeddings is not None:
        dense_vector = await cache.get_embedding(query)
        if dense_vector is None:
            sparse_cached = await cache.get_sparse_embedding(query)
            if sparse_cached is not None:
                # Dense miss, sparse cached → just compute dense
                dense_vector = await embeddings.aembed_query(query)
                await cache.store_embedding(query, dense_vector)
                sparse_vector = sparse_cached
            elif callable(
                getattr(embeddings, "aembed_hybrid", None)
            ) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid):
                # Hybrid: single call for both dense + sparse
                dense_vector, sparse_vector = await embeddings.aembed_hybrid(query)
                await cache.store_embedding(query, dense_vector)
                await cache.store_sparse_embedding(query, sparse_vector)
            else:
                # Fallback: parallel dense + sparse (old path)
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
    cached_results = await cache.get_search_results(dense_vector, search_cache_profile)
    if cached_results is not None:
        if needs_coverage:
            cached_results = cap_results_per_doc(cached_results, max_per_doc=2)
        latency = time.perf_counter() - start
        PipelineMetrics.get().record("retrieve", latency * 1000)
        logger.info("retrieve HIT search cache (%.3fs, %d docs)", latency, len(cached_results))
        cached_ctx = _build_retrieved_context(cached_results)
        distinct_doc_count = _distinct_doc_count(cached_results)
        lf.update_current_span(
            output={
                "results_count": len(cached_results),
                "search_cache_hit": True,
                "needs_coverage": needs_coverage,
                "coverage_reason": coverage_decision.reason,
                "distinct_doc_count": distinct_doc_count,
                "coverage_grouping_applied": needs_coverage,
                "duration_ms": round(latency * 1000, 1),
                # Full data for Langfuse managed evaluators (#386)
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
            "rerank_applied": False,
            "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
            # Clear stale backend-error markers from previous turns/branches.
            "retrieval_backend_error": False,
            "retrieval_error_type": None,
            "retrieved_context": _build_retrieved_context(cached_results),
            "needs_coverage": needs_coverage,
        }

    # Step 2: Get sparse embedding (cached or compute)
    if sparse_vector is None:
        sparse_vector = await cache.get_sparse_embedding(query)
        if sparse_vector is None:
            sparse_vector = await sparse_embeddings.aembed_query(query)
            await cache.store_sparse_embedding(query, sparse_vector)

    # Step 3: Hybrid search via Qdrant SDK
    if needs_coverage:
        qdrant_result = await qdrant.hybrid_search_rrf(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            top_k=10,
            prefetch_multiplier=7,
            group_by="metadata.doc_id",
            group_size=2,
            return_meta=True,
        )
        rerank_applied = False
    elif colbert_query and _has_colbert_search:
        # 3-stage: dense+sparse -> RRF -> ColBERT MaxSim (server-side)
        qdrant_result = await qdrant.hybrid_search_rrf_colbert(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            colbert_query=colbert_query,
            top_k=top_k,
            return_meta=True,
        )
        rerank_applied = True
    else:
        # 2-stage fallback: dense+sparse -> RRF
        qdrant_result = await qdrant.hybrid_search_rrf(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            top_k=top_k,
            return_meta=True,
        )
        rerank_applied = False
    if isinstance(qdrant_result, tuple) and len(qdrant_result) == 2:
        results, search_meta = qdrant_result
    else:
        # Backward compatibility: some mocks/adapters still return only result list.
        results = qdrant_result
        search_meta = {"backend_error": False, "error_type": None, "error_message": None}

    if needs_coverage and results:
        results = cap_results_per_doc(results, max_per_doc=2)

    # Step 4: Cache results (only on successful backend response)
    if results and not search_meta.get("backend_error", False):
        await cache.store_search_results(dense_vector, search_cache_profile, results)

    latency = time.perf_counter() - start
    PipelineMetrics.get().record("retrieve", latency * 1000)
    logger.info("retrieve done (%.3fs, %d docs)", latency, len(results))

    scores = [d.get("score", 0) for d in results if isinstance(d, dict)]
    result_ctx = _build_retrieved_context(results)
    distinct_doc_count = _distinct_doc_count(results)
    lf.update_current_span(
        output={
            "results_count": len(results),
            "top_score": round(scores[0], 4) if scores else None,
            "min_score": round(scores[-1], 4) if scores else None,
            "search_cache_hit": False,
            "needs_coverage": needs_coverage,
            "coverage_reason": coverage_decision.reason,
            "distinct_doc_count": distinct_doc_count,
            "coverage_grouping_applied": needs_coverage,
            "retrieval_backend_error": search_meta.get("backend_error", False),
            "retrieval_error_type": search_meta.get("error_type"),
            "duration_ms": round(latency * 1000, 1),
            # Full data for Langfuse managed evaluators (#386)
            "eval_query": query[:2000],
            "eval_docs": "\n\n".join(
                f"[{d.get('score', 0):.2f}] {str(d.get('content', ''))[:500]}" for d in result_ctx
            ),
        }
    )

    update: dict[str, Any] = {
        "documents": results,
        "search_results_count": len(results),
        "search_cache_hit": False,
        "sparse_embedding": sparse_vector,
        "rerank_applied": rerank_applied,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
        "retrieval_backend_error": search_meta.get("backend_error", False),
        "retrieval_error_type": search_meta.get("error_type"),
        "retrieved_context": _build_retrieved_context(results),
        "needs_coverage": needs_coverage,
    }
    # Persist re-computed embedding for downstream nodes (grade, cache_store)
    if state.get("query_embedding") is None and dense_vector:
        update["query_embedding"] = dense_vector
    return update
