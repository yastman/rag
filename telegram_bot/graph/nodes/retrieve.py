"""Retrieve node for RAG LangGraph pipeline.

Performs hybrid RRF search via QdrantService with search cache integration.
Uses direct Qdrant SDK (NOT langchain_qdrant) for full control over
prefetch, FusionQuery, and ColBERT reranking.
"""

from __future__ import annotations

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
        top_k: Number of results to retrieve

    Returns:
        State update with documents, search_results_count, sparse_embedding
    """
    query = (
        state["messages"][-1].content
        if hasattr(state["messages"][-1], "content")
        else state["messages"][-1]["content"]
    )
    dense_vector = state.get("query_embedding", [])

    start = time.time()

    # Step 1: Check search cache
    cached_results = await cache.get_search_results(dense_vector)
    if cached_results is not None:
        latency = (time.time() - start) * 1000
        logger.info("retrieve HIT search cache (%.0fms, %d docs)", latency, len(cached_results))
        return {
            "documents": cached_results,
            "search_results_count": len(cached_results),
            "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
        }

    # Step 2: Get sparse embedding (cached or compute)
    sparse_vector = await cache.get_sparse_embedding(query)
    if sparse_vector is None:
        sparse_vector = await sparse_embeddings.aembed_query(query)
        await cache.store_sparse_embedding(query, sparse_vector)

    # Step 3: Hybrid search via Qdrant SDK (RRF fusion)
    results = await qdrant.hybrid_search_rrf(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        top_k=top_k,
    )

    # Step 4: Cache results
    if results:
        await cache.store_search_results(dense_vector, None, results)

    latency = (time.time() - start) * 1000
    logger.info("retrieve done (%.0fms, %d docs)", latency, len(results))

    return {
        "documents": results,
        "search_results_count": len(results),
        "sparse_embedding": sparse_vector,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
    }
