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

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

_MAX_CONTEXT_SNIPPET = 500  # chars per doc for judge evaluation


def _build_retrieved_context(
    results: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, str | float]]:
    """Build curated context snippets for LLM-as-a-Judge evaluation."""
    ctx: list[dict[str, str | float]] = []
    for doc in results[:limit]:
        if not isinstance(doc, dict):
            continue
        text = doc.get("text", "")
        ctx.append(
            {
                "content": text[:_MAX_CONTEXT_SNIPPET],
                "score": doc.get("score", 0),
            }
        )
    return ctx


@observe(name="node-retrieve", capture_input=False, capture_output=False)
async def retrieve_node(
    state: dict[str, Any],
    *,
    cache: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    embeddings: Any | None = None,
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
        cache: CacheLayerManager instance
        sparse_embeddings: BGEM3SparseEmbeddings instance
        qdrant: QdrantService instance
        embeddings: Optional BGEM3Embeddings for re-embedding after rewrite
        top_k: Number of results to retrieve

    Returns:
        State update with documents, search_results_count, sparse_embedding
    """
    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )

    # Curated span metadata (replaces auto-captured full state)
    lf = get_client()
    lf.update_current_span(
        input={
            "query_preview": query[:120],
            "query_len": len(query),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
            "query_type": state.get("query_type"),
            "top_k": top_k,
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
    cached_results = await cache.get_search_results(dense_vector)
    if cached_results is not None:
        latency = time.perf_counter() - start
        logger.info("retrieve HIT search cache (%.3fs, %d docs)", latency, len(cached_results))
        lf.update_current_span(
            output={
                "results_count": len(cached_results),
                "search_cache_hit": True,
                "duration_ms": round(latency * 1000, 1),
            }
        )
        return {
            "documents": cached_results,
            "search_results_count": len(cached_results),
            "search_cache_hit": True,
            "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
            # Clear stale backend-error markers from previous turns/branches.
            "retrieval_backend_error": False,
            "retrieval_error_type": None,
            "retrieved_context": _build_retrieved_context(cached_results),
        }

    # Step 2: Get sparse embedding (cached or compute)
    if sparse_vector is None:
        sparse_vector = await cache.get_sparse_embedding(query)
        if sparse_vector is None:
            sparse_vector = await sparse_embeddings.aembed_query(query)
            await cache.store_sparse_embedding(query, sparse_vector)

    # Step 3: Hybrid search via Qdrant SDK (RRF fusion)
    qdrant_result = await qdrant.hybrid_search_rrf(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        top_k=top_k,
        return_meta=True,
    )
    if isinstance(qdrant_result, tuple) and len(qdrant_result) == 2:
        results, search_meta = qdrant_result
    else:
        # Backward compatibility: some mocks/adapters still return only result list.
        results = qdrant_result
        search_meta = {"backend_error": False, "error_type": None, "error_message": None}

    # Step 4: Cache results (only on successful backend response)
    if results and not search_meta.get("backend_error", False):
        await cache.store_search_results(dense_vector, None, results)

    latency = time.perf_counter() - start
    logger.info("retrieve done (%.3fs, %d docs)", latency, len(results))

    scores = [d.get("score", 0) for d in results if isinstance(d, dict)]
    lf.update_current_span(
        output={
            "results_count": len(results),
            "top_score": round(scores[0], 4) if scores else None,
            "min_score": round(scores[-1], 4) if scores else None,
            "search_cache_hit": False,
            "retrieval_backend_error": search_meta.get("backend_error", False),
            "retrieval_error_type": search_meta.get("error_type"),
            "duration_ms": round(latency * 1000, 1),
        }
    )

    update: dict[str, Any] = {
        "documents": results,
        "search_results_count": len(results),
        "search_cache_hit": False,
        "sparse_embedding": sparse_vector,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
        "retrieval_backend_error": search_meta.get("backend_error", False),
        "retrieval_error_type": search_meta.get("error_type"),
        "retrieved_context": _build_retrieved_context(results),
    }
    # Persist re-computed embedding for downstream nodes (grade, cache_store)
    if state.get("query_embedding") is None and dense_vector:
        update["query_embedding"] = dense_vector
    return update
