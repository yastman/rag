"""Unified HTTP client for BGE-M3 API endpoints.

Single internal SDK layer for all BGE-M3 interactions:
- /encode/dense  — dense embeddings (1024-dim)
- /encode/sparse — sparse embeddings (lexical_weights)
- /encode/hybrid — combined dense + sparse in one call
- /rerank        — ColBERT MaxSim reranking

Centralizes: httpx client lifecycle, retry/timeout policy, response parsing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


logger = logging.getLogger(__name__)

# Transient transport errors worth retrying
RETRYABLE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

_bge_retry = retry(
    retry=retry_if_exception_type(RETRYABLE_ERRORS),
    wait=wait_exponential_jitter(initial=0.5, max=4, jitter=1),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
DEFAULT_BATCH_SIZE = 32
DEFAULT_MAX_LENGTH = 512


@dataclass
class DenseResult:
    """Result from /encode/dense."""

    vectors: list[list[float]]
    processing_time: float | None = None


@dataclass
class SparseResult:
    """Result from /encode/sparse."""

    weights: list[dict[str, Any]]
    processing_time: float | None = None


@dataclass
class HybridResult:
    """Result from /encode/hybrid."""

    dense_vecs: list[list[float]]
    lexical_weights: list[dict[str, Any]]
    colbert_vecs: list[list[list[float]]] | None = None
    processing_time: float | None = None


@dataclass
class RerankResult:
    """Result from /rerank."""

    results: list[dict[str, Any]] = field(default_factory=list)
    processing_time: float | None = None


@dataclass
class ColbertResult:
    """Result from /encode/colbert."""

    colbert_vecs: list[list[list[float]]]
    processing_time: float | None = None


class BGEM3Client:
    """Async HTTP client for BGE-M3 API.

    Usage::

        client = BGEM3Client("http://bge-m3:8000")
        result = await client.encode_dense(["hello world"])
        vectors = result.vectors  # [[0.1, 0.2, ...]]
        await client.aclose()
    """

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: httpx.Timeout | float | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_length = max_length
        self.batch_size = batch_size
        if timeout is None:
            self._timeout = DEFAULT_TIMEOUT
        elif isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(timeout)
        else:
            self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    @_bge_retry
    async def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors via /encode/dense."""
        if not texts:
            return DenseResult(vectors=[])
        client = self._get_client()
        all_vecs: list[list[float]] = []
        processing_time: float | None = None
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = await client.post(
                f"{self.base_url}/encode/dense",
                json={"texts": batch, "batch_size": len(batch), "max_length": self.max_length},
            )
            resp.raise_for_status()
            data = resp.json()
            all_vecs.extend(data["dense_vecs"])
            processing_time = data.get("processing_time")
        return DenseResult(vectors=all_vecs, processing_time=processing_time)

    @_bge_retry
    async def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors via /encode/sparse."""
        if not texts:
            return SparseResult(weights=[])
        client = self._get_client()
        all_weights: list[dict[str, Any]] = []
        processing_time: float | None = None
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = await client.post(
                f"{self.base_url}/encode/sparse",
                json={"texts": batch, "batch_size": len(batch), "max_length": self.max_length},
            )
            resp.raise_for_status()
            data = resp.json()
            all_weights.extend(data["lexical_weights"])
            processing_time = data.get("processing_time")
        return SparseResult(weights=all_weights, processing_time=processing_time)

    @_bge_retry
    async def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse via /encode/hybrid (single call)."""
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        client = self._get_client()
        resp = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": texts, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return HybridResult(
            dense_vecs=data["dense_vecs"],
            lexical_weights=data["lexical_weights"],
            colbert_vecs=data.get("colbert_vecs"),
            processing_time=data.get("processing_time"),
        )

    @_bge_retry
    async def rerank(self, query: str, documents: list[str], top_k: int = 5) -> RerankResult:
        """Rerank documents via ColBERT MaxSim /rerank endpoint."""
        if not documents:
            return RerankResult()
        client = self._get_client()
        resp = await client.post(
            f"{self.base_url}/rerank",
            json={
                "query": query,
                "documents": documents,
                "top_k": top_k,
                "max_length": self.max_length,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return RerankResult(
            results=[{"index": r["index"], "score": r["score"]} for r in data["results"]],
            processing_time=data.get("processing_time"),
        )

    @_bge_retry
    async def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors via /encode/colbert."""
        if not texts:
            return ColbertResult(colbert_vecs=[])
        client = self._get_client()
        resp = await client.post(
            f"{self.base_url}/encode/colbert",
            json={"texts": texts, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return ColbertResult(
            colbert_vecs=data["colbert_vecs"],
            processing_time=data.get("processing_time"),
        )

    async def health(self) -> bool:
        """Check BGE-M3 service health."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class BGEM3SyncClient:
    """Synchronous HTTP client for BGE-M3 API.

    Used by ingestion pipeline (CocoIndex requires sync operations).
    """

    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 300.0,
        max_length: int = DEFAULT_MAX_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_length = max_length
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=timeout)

    def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors (sync)."""
        if not texts:
            return DenseResult(vectors=[])
        all_vecs: list[list[float]] = []
        processing_time: float | None = None
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self._client.post(
                f"{self.base_url}/encode/dense",
                json={"texts": batch, "batch_size": len(batch), "max_length": self.max_length},
            )
            resp.raise_for_status()
            data = resp.json()
            all_vecs.extend(data["dense_vecs"])
            processing_time = data.get("processing_time")
        return DenseResult(vectors=all_vecs, processing_time=processing_time)

    def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors (sync)."""
        if not texts:
            return SparseResult(weights=[])
        all_weights: list[dict[str, Any]] = []
        processing_time: float | None = None
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self._client.post(
                f"{self.base_url}/encode/sparse",
                json={"texts": batch, "batch_size": len(batch), "max_length": self.max_length},
            )
            resp.raise_for_status()
            data = resp.json()
            all_weights.extend(data["lexical_weights"])
            processing_time = data.get("processing_time")
        return SparseResult(weights=all_weights, processing_time=processing_time)

    def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors (sync)."""
        if not texts:
            return ColbertResult(colbert_vecs=[])
        resp = self._client.post(
            f"{self.base_url}/encode/colbert",
            json={"texts": texts, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return ColbertResult(
            colbert_vecs=data["colbert_vecs"],
            processing_time=data.get("processing_time"),
        )

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()
