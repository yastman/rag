"""Canonical BGE-M3 embedding provider adapter.

This module owns the runtime-facing embedding provider surface.  It adapts the
low-level :class:`src.services.bge_m3_client.BGEM3Client` HTTP SDK into the
method shapes used by retrieval, semantic cache, and legacy LangChain shims.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import httpx

from src.adapters.embeddings.base import EmbeddingProvider
from src.services.bge_m3_client import BGEM3Client


class BgeM3EmbeddingProvider(EmbeddingProvider):
    """BGE-M3 provider for dense, sparse, hybrid, and ColBERT query vectors.

    ``BGEM3Client`` remains the low-level REST SDK.  This provider is the
    canonical adapter layer consumed by runtime retrieval code and compatibility
    wrappers, so callers do not need to know BGE-M3 endpoint details.
    """

    def __init__(
        self,
        client: BGEM3Client | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        batch_size: int = 32,
        max_length: int = 512,
    ) -> None:
        url = base_url or os.getenv("BGE_M3_URL", "http://bge-m3:8000") or "http://bge-m3:8000"
        self.base_url = url
        self.timeout = timeout
        self._client = client or BGEM3Client(
            base_url=url,
            timeout=timeout,
            max_length=max_length,
            batch_size=batch_size,
        )

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute dense embeddings for a sequence of texts."""
        return await self.aembed_documents(list(texts))

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Compute dense document embeddings."""
        if not texts:
            return []
        result = await self._client.encode_dense(texts)
        return result.vectors

    async def aembed_query(self, text: str) -> list[float]:
        """Compute a dense query embedding."""
        result = await self._client.encode_dense([text])
        return result.vectors[0]

    async def aembed_dense_query(self, text: str) -> tuple[list[float], float | None]:
        """Compute a dense query embedding and expose BGE processing time."""
        result = await self._client.encode_dense([text])
        return result.vectors[0], result.processing_time

    async def aembed_sparse_query(self, text: str) -> dict[str, Any]:
        """Compute a sparse query vector."""
        result = await self._client.encode_sparse([text])
        return result.weights[0]

    async def aembed_sparse_documents(self, texts: list[str]) -> list[dict[str, Any]]:
        """Compute sparse document vectors."""
        if not texts:
            return []
        result = await self._client.encode_sparse(texts)
        return result.weights

    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Compute dense and sparse query vectors in one provider call."""
        result = await self._client.encode_hybrid([text])
        return result.dense_vecs[0], result.lexical_weights[0]

    async def aembed_hybrid_with_colbert(
        self, text: str
    ) -> tuple[list[float], dict[str, Any], list[list[float]]]:
        """Compute dense, sparse, and ColBERT query vectors.

        Prefer the BGE-M3 hybrid endpoint when it returns ColBERT vectors; fall
        back to the dedicated ColBERT endpoint for older service builds.
        """
        result = await self._client.encode_hybrid([text])
        dense = result.dense_vecs[0]
        sparse = result.lexical_weights[0]

        if result.colbert_vecs:
            colbert = result.colbert_vecs[0]
        else:
            colbert_result = await self._client.encode_colbert([text])
            colbert = colbert_result.colbert_vecs[0]

        return dense, sparse, colbert

    async def aembed_colbert_query(self, text: str) -> list[list[float]]:
        """Compute ColBERT query token vectors."""
        result = await self._client.encode_colbert([text])
        return result.colbert_vecs[0]

    async def aembed_hybrid_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        """Compute dense and sparse vectors for a batch of texts."""
        if not texts:
            return [], []
        result = await self._client.encode_hybrid(texts)
        return result.dense_vecs, result.lexical_weights

    async def aclose(self) -> None:
        """Close the underlying BGE-M3 client."""
        await self._client.aclose()
