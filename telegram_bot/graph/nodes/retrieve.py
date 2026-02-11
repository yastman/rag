"""Retrieve node for RAG LangGraph pipeline.

Performs hybrid RRF search via QdrantService with search cache integration.
Uses direct Qdrant SDK (NOT langchain_qdrant) for full control over
prefetch, FusionQuery, and ColBERT reranking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


@observe(name="node-retrieve")
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
    query = (
        state["messages"][-1].content
        if hasattr(state["messages"][-1], "content")
        else state["messages"][-1]["content"]
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
        return {
            "documents": cached_results,
            "search_results_count": len(cached_results),
            "search_cache_hit": True,
            "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
            # Clear stale backend-error markers from previous turns/branches.
            "retrieval_backend_error": False,
            "retrieval_error_type": None,
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

    update: dict[str, Any] = {
        "documents": results,
        "search_results_count": len(results),
        "search_cache_hit": False,
        "sparse_embedding": sparse_vector,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
        "retrieval_backend_error": search_meta.get("backend_error", False),
        "retrieval_error_type": search_meta.get("error_type"),
    }
    # Persist re-computed embedding for downstream nodes (grade, cache_store)
    if state.get("query_embedding") is None and dense_vector:
        update["query_embedding"] = dense_vector
    return update
