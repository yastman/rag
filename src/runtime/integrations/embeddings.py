"""Runtime compatibility wrappers for embedding providers.

The canonical embedding adapter layer is ``src.adapters.embeddings``. This
module keeps the historical runtime class names used by legacy imports, but all
BGE-M3 endpoint work is delegated to ``BgeM3EmbeddingProvider``.
``BGEM3Client`` remains the low-level HTTP SDK.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider
from src.observability import observe
from src.services.bge_m3_client import BGEM3Client


class BGEM3Embeddings:
    """Dense-embedding compatibility shim over the canonical BGE-M3 provider."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        batch_size: int = 32,
        max_length: int = 512,
        *,
        client: BGEM3Client | None = None,
        provider: BgeM3EmbeddingProvider | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._provider = provider or BgeM3EmbeddingProvider(
            client=client,
            base_url=base_url,
            timeout=timeout,
            max_length=max_length,
            batch_size=batch_size,
        )

    @observe(name="bge-m3-dense-embed", capture_input=False, capture_output=False)
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._provider.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await self._provider.aembed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))

    async def aclose(self) -> None:
        await self._provider.aclose()


class BGEM3SparseEmbeddings:
    """Sparse-embedding compatibility shim over the canonical BGE-M3 provider."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        max_length: int = 512,
        *,
        client: BGEM3Client | None = None,
        provider: BgeM3EmbeddingProvider | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._provider = provider or BgeM3EmbeddingProvider(
            client=client,
            base_url=base_url,
            timeout=timeout,
            max_length=max_length,
        )

    @observe(name="bge-m3-sparse-embed", capture_input=False, capture_output=False)
    async def aembed_query(self, text: str) -> dict[str, Any]:
        return await self._provider.aembed_sparse_query(text)

    @observe(name="bge-m3-sparse-embed-batch", capture_input=False, capture_output=False)
    async def aembed_documents(self, texts: list[str]) -> list[dict[str, Any]]:
        return await self._provider.aembed_sparse_documents(texts)

    async def aclose(self) -> None:
        await self._provider.aclose()


class BGEM3HybridEmbeddings:
    """Hybrid/ColBERT compatibility shim over the canonical BGE-M3 provider."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float | httpx.Timeout | None = None,
        max_length: int = 512,
        *,
        client: BGEM3Client | None = None,
        provider: BgeM3EmbeddingProvider | None = None,
    ) -> None:
        self._provider = provider or BgeM3EmbeddingProvider(
            client=client,
            base_url=base_url,
            timeout=timeout,
            max_length=max_length,
        )

    @observe(name="bge-m3-dense-query-embed", capture_input=False, capture_output=False)
    async def aembed_dense_query(self, text: str) -> tuple[list[float], float | None]:
        """Embed query text via BGE-M3, returning ``(dense_vector, processing_time)``."""
        return await self._provider.aembed_dense_query(text)

    @observe(name="bge-m3-hybrid-embed", capture_input=False, capture_output=False)
    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Embed text, returning ``(dense, sparse)``."""
        return await self._provider.aembed_hybrid(text)

    @observe(name="bge-m3-hybrid-colbert-embed", capture_input=False, capture_output=False)
    async def aembed_hybrid_with_colbert(
        self, text: str
    ) -> tuple[list[float], dict[str, Any], list[list[float]]]:
        """Embed text, returning ``(dense, sparse, colbert_query_vectors)``."""
        return await self._provider.aembed_hybrid_with_colbert(text)

    @observe(name="bge-m3-colbert-query-embed", capture_input=False, capture_output=False)
    async def aembed_colbert_query(self, text: str) -> list[list[float]]:
        """Embed text, returning ColBERT query token vectors only."""
        return await self._provider.aembed_colbert_query(text)

    @observe(name="bge-m3-hybrid-embed-batch", capture_input=False, capture_output=False)
    async def aembed_hybrid_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        """Batch embed dense and sparse vectors."""
        return await self._provider.aembed_hybrid_batch(texts)

    async def aembed_query(self, text: str) -> list[float]:
        dense, _ = await self.aembed_hybrid(text)
        return dense

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        dense_vecs, _ = await self.aembed_hybrid_batch(texts)
        return dense_vecs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))

    async def aclose(self) -> None:
        await self._provider.aclose()


__all__ = [
    "BGEM3Embeddings",
    "BGEM3HybridEmbeddings",
    "BGEM3SparseEmbeddings",
]
