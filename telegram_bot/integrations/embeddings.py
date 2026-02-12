"""LangChain Embeddings wrappers for BGE-M3 API.

Provides BGEM3Embeddings (dense) and BGEM3SparseEmbeddings (sparse)
that wrap the local BGE-M3 REST API for use in LangGraph pipelines.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)

# Transient transport errors worth retrying
_RETRYABLE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)

_embed_retry = retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    wait=wait_exponential_jitter(initial=0.5, max=4, jitter=1),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class BGEM3Embeddings(Embeddings):
    """LangChain Embeddings wrapper for BGE-M3 /encode/dense endpoint."""

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        batch_size: int = 32,
        max_length: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.batch_size = batch_size
        self.max_length = max_length

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout)

    @observe(name="bge-m3-dense-embed")
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        async with self._make_client() as client:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                response = await client.post(
                    f"{self.base_url}/encode/dense",
                    json={
                        "texts": batch,
                        "batch_size": len(batch),
                        "max_length": self.max_length,
                    },
                )
                response.raise_for_status()
                data = response.json()
                all_embeddings.extend(data["dense_vecs"])
        return all_embeddings

    async def aembed_query(self, text: str) -> list[float]:
        result = await self.aembed_documents([text])
        return result[0]

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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_length = max_length

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout)

    @observe(name="bge-m3-sparse-embed")
    async def aembed_query(self, text: str) -> dict[str, Any]:
        async with self._make_client() as client:
            response = await client.post(
                f"{self.base_url}/encode/sparse",
                json={"texts": [text], "max_length": self.max_length},
            )
            response.raise_for_status()
            data: dict[str, list[dict[str, Any]]] = response.json()
            return data["lexical_weights"][0]

    @observe(name="bge-m3-sparse-embed-batch")
    async def aembed_documents(self, texts: list[str]) -> list[dict[str, Any]]:
        if not texts:
            return []
        async with self._make_client() as client:
            response = await client.post(
                f"{self.base_url}/encode/sparse",
                json={"texts": texts, "max_length": self.max_length},
            )
            response.raise_for_status()
            data: dict[str, list[dict[str, Any]]] = response.json()
            return data["lexical_weights"]


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_length = max_length
        if timeout is None:
            self._timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        elif isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(timeout)
        else:
            self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=httpx.AsyncHTTPTransport(retries=1),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    @observe(name="bge-m3-hybrid-embed")
    @_embed_retry
    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Embed text via /encode/hybrid, returning (dense, sparse)."""
        client = self._get_client()
        response = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": [text], "max_length": self.max_length},
        )
        response.raise_for_status()
        data = response.json()
        dense = data["dense_vecs"][0]
        sparse = data["lexical_weights"][0]
        return dense, sparse

    @observe(name="bge-m3-hybrid-embed-batch")
    @_embed_retry
    async def aembed_hybrid_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        """Batch embed via /encode/hybrid."""
        if not texts:
            return [], []
        client = self._get_client()
        response = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": texts, "max_length": self.max_length},
        )
        response.raise_for_status()
        data = response.json()
        return data["dense_vecs"], data["lexical_weights"]

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
        if self._client and not self._client.is_closed:
            await self._client.aclose()
