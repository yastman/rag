"""Pure retrieval service boundary for runtime RAG.

This module creates the seam requested by #2406: retrieval owns query
vectorization plus Qdrant lookup, while answer generation stays outside this
package.  It intentionally delegates algorithms to the existing Qdrant gateway
instead of changing ranking behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.embeddings.base import EmbeddingProvider
from src.runtime.services.qdrant import QdrantService, SearchReturn


@dataclass(frozen=True)
class RetrievalRequest:
    """Input contract for pure retrieval."""

    query: str
    filters: dict[str, Any] | None = None
    top_k: int = 5
    return_meta: bool = False


class RetrievalService:
    """Compose embeddings and Qdrant into a generation-free retrieval layer."""

    def __init__(self, *, embeddings: EmbeddingProvider, qdrant: QdrantService) -> None:
        self._embeddings = embeddings
        self._qdrant = qdrant

    async def retrieve(self, request: RetrievalRequest) -> SearchReturn:
        """Retrieve documents for a query without invoking answer generation.

        The preferred path asks the embedding provider for dense+sparse+ColBERT
        vectors and uses the canonical ``QdrantService`` ColBERT/RRF gateway.
        Providers without ColBERT support fall back to dense+sparse RRF, and
        dense-only providers fall back to dense search through RRF with no
        sparse vector.
        """
        colbert_vectors: tuple[list[float], dict[str, Any], list[list[float]]] | None = None
        try:
            colbert_vectors = await self._embeddings.aembed_hybrid_with_colbert(request.query)
        except NotImplementedError:
            colbert_vectors = None

        if colbert_vectors is not None:
            dense, sparse, colbert = colbert_vectors
            return await self._qdrant.hybrid_search_rrf_colbert(
                dense_vector=dense,
                sparse_vector=sparse,
                colbert_query=colbert,
                filters=request.filters,
                top_k=request.top_k,
                return_meta=request.return_meta,
            )

        hybrid_vectors: tuple[list[float], dict[str, Any]] | None = None
        try:
            hybrid_vectors = await self._embeddings.aembed_hybrid(request.query)
        except NotImplementedError:
            hybrid_vectors = None

        if hybrid_vectors is not None:
            dense, sparse = hybrid_vectors
        else:
            dense = await self._embeddings.aembed_query(request.query)
            sparse = None

        return await self._qdrant.hybrid_search_rrf(
            dense_vector=dense,
            sparse_vector=sparse,
            filters=request.filters,
            top_k=request.top_k,
            return_meta=request.return_meta,
        )
