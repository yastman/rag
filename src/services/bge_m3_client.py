"""Unified HTTP client for BGE-M3 API endpoints.

Single internal SDK layer for all BGE-M3 interactions:
- /encode/dense  — dense embeddings (1024-dim)
- /encode/sparse — sparse embeddings (lexical_weights)
- /encode/hybrid — combined dense + sparse (+ optional ColBERT) in one call
- /encode/colbert — ColBERT multivectors
- /rerank        — ColBERT MaxSim reranking

Centralizes: httpx client lifecycle, retry/timeout policy, response parsing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from itertools import batched
from typing import Any

import httpx

from src.services._retry import bge_retry


DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
DEFAULT_BATCH_SIZE = 32
DEFAULT_MAX_LENGTH = 512
BGE_M3_MODEL_NAME = "BAAI/bge-m3"


def _request_batches(texts: list[str]) -> list[tuple[int, list[str]]]:
    """Split one logical encode operation into ordered, sidecar-safe requests."""
    return [
        (offset * DEFAULT_BATCH_SIZE, list(batch))
        for offset, batch in enumerate(batched(texts, DEFAULT_BATCH_SIZE))
    ]


def _batch_metadata(
    results: list[tuple[int, Any]],
) -> dict[str, float | list[dict[str, Any]] | None]:
    """Aggregate timing and restore partial-failure indices to input coordinates."""
    processing_times = [
        result.processing_time for _, result in results if result.processing_time is not None
    ]
    return {
        "processing_time": sum(processing_times) if processing_times else None,
        "partial_failures": [
            {**failure, "index": failure["index"] + offset}
            for offset, result in results
            for failure in result.partial_failures
        ],
    }


def _build_payload(
    texts: list[str],
    batch_size: int,
    max_length: int,
) -> dict[str, Any]:
    """Build the standard encode request payload shared by all encode endpoints."""
    return {"texts": texts, "batch_size": batch_size, "max_length": max_length}


def _parse_dense_response(data: dict[str, Any]) -> DenseResult:
    """Parse /encode/dense response JSON into DenseResult."""
    return DenseResult(
        vectors=data["dense_vecs"],
        processing_time=data.get("processing_time"),
        partial_failures=data.get("partial_failures", []),
    )


def _parse_sparse_response(data: dict[str, Any]) -> SparseResult:
    """Parse /encode/sparse response JSON into SparseResult."""
    return SparseResult(
        weights=data["lexical_weights"],
        processing_time=data.get("processing_time"),
        partial_failures=data.get("partial_failures", []),
    )


def _parse_colbert_response(data: dict[str, Any]) -> ColbertResult:
    """Parse /encode/colbert response JSON into ColbertResult."""
    return ColbertResult(
        colbert_vecs=data["colbert_vecs"],
        processing_time=data.get("processing_time"),
        partial_failures=data.get("partial_failures", []),
    )


def _parse_hybrid_response(data: dict[str, Any]) -> HybridResult:
    """Parse /encode/hybrid response JSON into HybridResult."""
    return HybridResult(
        dense_vecs=data["dense_vecs"],
        lexical_weights=data["lexical_weights"],
        colbert_vecs=data.get("colbert_vecs"),
        processing_time=data.get("processing_time"),
        partial_failures=data.get("partial_failures", []),
    )


@dataclass
class DenseResult:
    """Result from /encode/dense."""

    vectors: list[list[float]]
    processing_time: float | None = None
    partial_failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SparseResult:
    """Result from /encode/sparse."""

    weights: list[dict[str, Any]]
    processing_time: float | None = None
    partial_failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HybridResult:
    """Result from /encode/hybrid (dense + sparse + optional ColBERT)."""

    dense_vecs: list[list[float]]
    lexical_weights: list[dict[str, Any]]
    colbert_vecs: list[list[list[float]]] | None = None
    processing_time: float | None = None
    partial_failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RerankResult:
    """Result from /rerank."""

    results: list[dict[str, Any]] = field(default_factory=list)
    processing_time: float | None = None
    partial_failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ColbertResult:
    """Result from /encode/colbert."""

    colbert_vecs: list[list[list[float]]]
    processing_time: float | None = None
    partial_failures: list[dict[str, Any]] = field(default_factory=list)


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
        # Guards _get_client / aclose so concurrent reconnects after close do
        # not race in creating multiple AsyncClient instances. Created lazily
        # against the running loop so the lock is bound to the same event loop
        # that uses the client (#1641).
        self._client_lock: asyncio.Lock | None = None

    def _get_client_lock(self) -> asyncio.Lock:
        """Return the per-instance asyncio.Lock, creating it lazily.

        The lock is created lazily so BGEM3Client construction does not
        require a running event loop. asyncio.Lock binds to the running
        loop on first use.
        """
        if self._client_lock is None:
            self._client_lock = asyncio.Lock()
        return self._client_lock

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a connected httpx.AsyncClient, reconnecting if needed.

        Concurrent callers that arrive while ``self._client`` is ``None`` or
        closed all observe a single replacement AsyncClient: the lock guards
        the check-then-set window, and the post-lock re-check ensures only
        the first task constructs the new instance (#1641).
        """
        client = self._client
        if client is not None and not client.is_closed:
            return client
        async with self._get_client_lock():
            client = self._client
            if client is None or client.is_closed:
                # Note: a pre-closed client does not need explicit aclose().
                # We never replace a non-closed client here — the outer
                # check would have returned it already.
                client = httpx.AsyncClient(
                    timeout=self._timeout,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
                self._client = client
            return client

    async def _encode_batches(
        self, endpoint: str, texts: list[str], parser: Any
    ) -> list[tuple[int, Any]]:
        """Post every request batch for one logical encode operation."""
        client = await self._get_client()
        results = []
        for offset, batch in _request_batches(texts):
            resp = await client.post(
                f"{self.base_url}{endpoint}",
                json=_build_payload(batch, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            results.append((offset, parser(resp.json())))
        return results

    @staticmethod
    def _hybrid_colbert(results: list[tuple[int, HybridResult]]) -> list[list[list[float]]] | None:
        """Combine optional ColBERT vectors without changing the legacy absent value."""
        if all(result.colbert_vecs is None for _, result in results):
            return None
        return [vector for _, result in results for vector in result.colbert_vecs or []]

    @bge_retry
    async def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors via /encode/dense."""
        if not texts:
            return DenseResult(vectors=[])
        results = await self._encode_batches("/encode/dense", texts, _parse_dense_response)
        return DenseResult(
            vectors=[vector for _, result in results for vector in result.vectors],
            **_batch_metadata(results),
        )

    @bge_retry
    async def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors via /encode/sparse."""
        if not texts:
            return SparseResult(weights=[])
        results = await self._encode_batches("/encode/sparse", texts, _parse_sparse_response)
        return SparseResult(
            weights=[weight for _, result in results for weight in result.weights],
            **_batch_metadata(results),
        )

    @bge_retry
    async def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse (+ optional ColBERT) via /encode/hybrid."""
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        results = await self._encode_batches("/encode/hybrid", texts, _parse_hybrid_response)
        return HybridResult(
            dense_vecs=[vector for _, result in results for vector in result.dense_vecs],
            lexical_weights=[weight for _, result in results for weight in result.lexical_weights],
            colbert_vecs=self._hybrid_colbert(results),
            **_batch_metadata(results),
        )

    @bge_retry
    async def rerank(self, query: str, documents: list[str], top_k: int = 5) -> RerankResult:
        """Rerank documents via ColBERT MaxSim /rerank endpoint."""
        if not documents:
            return RerankResult()
        client = await self._get_client()
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
            partial_failures=data.get("partial_failures", []),
        )

    @bge_retry
    async def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors via /encode/colbert."""
        if not texts:
            return ColbertResult(colbert_vecs=[])
        results = await self._encode_batches("/encode/colbert", texts, _parse_colbert_response)
        return ColbertResult(
            colbert_vecs=[vector for _, result in results for vector in result.colbert_vecs],
            **_batch_metadata(results),
        )

    async def aclose(self) -> None:
        """Close the underlying httpx client.

        Coordinated with ``_get_client`` via the same asyncio.Lock so a
        concurrent reconnect cannot observe a half-closed client (#1641).
        """
        async with self._get_client_lock():
            client = self._client
            if client is not None and not client.is_closed:
                self._client = None
                await client.aclose()


class BGEM3SyncClient:
    """Synchronous HTTP client for BGE-M3 API.

    Used by ingestion pipeline (sync wrapper for blocking I/O contexts).
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

    def _encode_batches(
        self, endpoint: str, texts: list[str], parser: Any
    ) -> list[tuple[int, Any]]:
        """Post every request batch for one logical encode operation."""
        results = []
        for offset, batch in _request_batches(texts):
            resp = self._client.post(
                f"{self.base_url}{endpoint}",
                json=_build_payload(batch, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            results.append((offset, parser(resp.json())))
        return results

    @staticmethod
    def _hybrid_colbert(results: list[tuple[int, HybridResult]]) -> list[list[list[float]]] | None:
        """Combine optional ColBERT vectors without changing the legacy absent value."""
        if all(result.colbert_vecs is None for _, result in results):
            return None
        return [vector for _, result in results for vector in result.colbert_vecs or []]

    @bge_retry
    def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors (sync)."""
        if not texts:
            return DenseResult(vectors=[])
        results = self._encode_batches("/encode/dense", texts, _parse_dense_response)
        return DenseResult(
            vectors=[vector for _, result in results for vector in result.vectors],
            **_batch_metadata(results),
        )

    @bge_retry
    def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors (sync)."""
        if not texts:
            return SparseResult(weights=[])
        results = self._encode_batches("/encode/sparse", texts, _parse_sparse_response)
        return SparseResult(
            weights=[weight for _, result in results for weight in result.weights],
            **_batch_metadata(results),
        )

    @bge_retry
    def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors (sync)."""
        if not texts:
            return ColbertResult(colbert_vecs=[])
        results = self._encode_batches("/encode/colbert", texts, _parse_colbert_response)
        return ColbertResult(
            colbert_vecs=[vector for _, result in results for vector in result.colbert_vecs],
            **_batch_metadata(results),
        )

    @bge_retry
    def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse + ColBERT via /encode/hybrid."""
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        results = self._encode_batches("/encode/hybrid", texts, _parse_hybrid_response)
        return HybridResult(
            dense_vecs=[vector for _, result in results for vector in result.dense_vecs],
            lexical_weights=[weight for _, result in results for weight in result.lexical_weights],
            colbert_vecs=self._hybrid_colbert(results),
            **_batch_metadata(results),
        )

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> BGEM3SyncClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
