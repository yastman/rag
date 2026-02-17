"""LangChain Embeddings wrappers for BGE-M3 API.

Provides BGEM3Embeddings (dense) and BGEM3SparseEmbeddings (sparse)
that wrap the local BGE-M3 REST API for use in LangGraph pipelines.

All HTTP communication delegates to BGEM3Client (unified SDK layer).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings

from telegram_bot.observability import observe
from telegram_bot.services.bge_m3_client import BGEM3Client


logger = logging.getLogger(__name__)


class BGEM3Embeddings(Embeddings):
    """LangChain Embeddings wrapper for BGE-M3 /encode/dense endpoint."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        batch_size: int = 32,
        max_length: int = 512,
        *,
        client: BGEM3Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._client = client or BGEM3Client(
            base_url=base_url,
            timeout=timeout,
            max_length=max_length,
            batch_size=batch_size,
        )

    @observe(name="bge-m3-dense-embed")
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = await self._client.encode_dense(texts)
        return result.vectors

    async def aembed_query(self, text: str) -> list[float]:
        result = await self._client.encode_dense([text])
        return result.vectors[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))


class BGEM3SparseEmbeddings:
    """Sparse embeddings wrapper for BGE-M3 /encode/sparse endpoint."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        max_length: int = 512,
        *,
        client: BGEM3Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._client = client or BGEM3Client(
            base_url=base_url,
            timeout=timeout,
            max_length=max_length,
        )

    @observe(name="bge-m3-sparse-embed")
    async def aembed_query(self, text: str) -> dict[str, Any]:
        result = await self._client.encode_sparse([text])
        return result.weights[0]

    @observe(name="bge-m3-sparse-embed-batch")
    async def aembed_documents(self, texts: list[str]) -> list[dict[str, Any]]:
        if not texts:
            return []
        result = await self._client.encode_sparse(texts)
        return result.weights


class BGEM3HybridEmbeddings(Embeddings):
    """Combined dense+sparse embedding via BGE-M3 /encode/hybrid.

    Single HTTP call returns both dense and sparse vectors.
    Uses shared httpx.AsyncClient for connection pooling.
    """

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float | httpx.Timeout | None = None,
        max_length: int = 512,
        *,
        client: BGEM3Client | None = None,
    ) -> None:
        self._client = client or BGEM3Client(
            base_url=base_url,
            timeout=timeout,
            max_length=max_length,
        )

    @observe(name="bge-m3-hybrid-embed")
    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Embed text via /encode/hybrid, returning (dense, sparse)."""
        result = await self._client.encode_hybrid([text])
        return result.dense_vecs[0], result.lexical_weights[0]

    @observe(name="bge-m3-hybrid-embed-batch")
    async def aembed_hybrid_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        """Batch embed via /encode/hybrid."""
        if not texts:
            return [], []
        result = await self._client.encode_hybrid(texts)
        return result.dense_vecs, result.lexical_weights

    async def aembed_query(self, text: str) -> list[float]:
        dense, _ = await self.aembed_hybrid(text)
        return dense

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        dense_vecs, _ = await self.aembed_hybrid_batch(texts)
        return dense_vecs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(text))

    async def aclose(self) -> None:
        await self._client.aclose()
