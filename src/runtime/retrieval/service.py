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
class VectorRetrievalRequest:
    """Pre-vectorized retrieval request used by cache-aware orchestration.

    This contract keeps Qdrant search selection inside the pure retrieval
    boundary even when the caller already owns embedding/cache decisions.
    """

    dense_vector: list[float]
    sparse_vector: Any = None
    colbert_query: list[list[float]] | None = None
    filters: dict[str, Any] | None = None
    top_k: int = 5
    return_meta: bool = False
    dense_weight: float | None = None
    sparse_weight: float | None = None


@dataclass(frozen=True)
class RetrievalRequest:
    """Input contract for pure retrieval."""

    query: str
    filters: dict[str, Any] | None = None
    top_k: int = 5
    return_meta: bool = False


class RetrievalService:
    """Compose embeddings and Qdrant into a generation-free retrieval layer."""

    def __init__(
        self, *, embeddings: EmbeddingProvider | None = None, qdrant: QdrantService
    ) -> None:
        self._embeddings = embeddings
        self._qdrant = qdrant

    async def retrieve_vectors(self, request: VectorRetrievalRequest) -> SearchReturn:
        """Retrieve documents for already-computed query vectors.

        Cache-aware pipelines may compute or reuse query vectors before the
        Qdrant call.  They still route the actual retrieval operation through
        this service so the RAG orchestrator does not own Qdrant search-method
        selection or answer generation.
        """
        search_kwargs: dict[str, Any] = {
            "dense_vector": request.dense_vector,
            "sparse_vector": request.sparse_vector,
            "filters": request.filters,
            "top_k": request.top_k,
            "return_meta": request.return_meta,
        }
        if request.dense_weight is not None:
            search_kwargs["dense_weight"] = request.dense_weight
        if request.sparse_weight is not None:
            search_kwargs["sparse_weight"] = request.sparse_weight

        has_colbert_search = callable(getattr(self._qdrant, "hybrid_search_rrf_colbert", None))
        if request.colbert_query and has_colbert_search:
            return await self._qdrant.hybrid_search_rrf_colbert(
                **search_kwargs,
                colbert_query=request.colbert_query,
            )

        return await self._qdrant.hybrid_search_rrf(**search_kwargs)

    async def retrieve(self, request: RetrievalRequest) -> SearchReturn:
        """Retrieve documents for a query without invoking answer generation.

        The preferred path asks the embedding provider for dense+sparse+ColBERT
        vectors and uses the canonical ``QdrantService`` ColBERT/RRF gateway.
        Providers without ColBERT support fall back to dense+sparse RRF, and
        dense-only providers fall back to dense search through RRF with no
        sparse vector.
        """
        if self._embeddings is None:
            raise RuntimeError("RetrievalService.retrieve requires an embedding provider")

        sparse: dict[str, Any] | None
        colbert_vectors: tuple[list[float], dict[str, Any], list[list[float]]] | None = None
        try:
            colbert_vectors = await self._embeddings.aembed_hybrid_with_colbert(request.query)
        except NotImplementedError:
            colbert_vectors = None

        if colbert_vectors is not None:
            dense, sparse, colbert = colbert_vectors
            return await self.retrieve_vectors(
                VectorRetrievalRequest(
                    dense_vector=dense,
                    sparse_vector=sparse,
                    colbert_query=colbert,
                    filters=request.filters,
                    top_k=request.top_k,
                    return_meta=request.return_meta,
                )
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

        return await self.retrieve_vectors(
            VectorRetrievalRequest(
                dense_vector=dense,
                sparse_vector=sparse,
                filters=request.filters,
                top_k=request.top_k,
                return_meta=request.return_meta,
            )
        )
