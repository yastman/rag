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
from typing import Any

import httpx

from src.observability import get_client, observe
from src.services._retry import bge_retry


DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
DEFAULT_BATCH_SIZE = 32
DEFAULT_MAX_LENGTH = 512
BGE_M3_MODEL_NAME = "BAAI/bge-m3"


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
    """Result from /encode/hybrid (dense + sparse + optional ColBERT)."""

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

    @observe(
        name="bge-m3-encode-dense", as_type="embedding", capture_input=False, capture_output=False
    )
    @bge_retry
    async def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors via /encode/dense."""
        lf = get_client()
        lf.update_current_span(
            input={
                "texts_count": len(texts),
                "batch_size": self.batch_size,
                "max_length": self.max_length,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        if not texts:
            lf.update_current_span(
                output={"vectors_count": 0, "vector_dim": 0},
                metadata={"model": BGE_M3_MODEL_NAME},
            )
            return DenseResult(vectors=[])
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/encode/dense",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        all_vecs = data["dense_vecs"]
        processing_time = data.get("processing_time")
        lf.update_current_span(
            output={
                "vectors_count": len(all_vecs),
                "vector_dim": len(all_vecs[0]) if all_vecs else 0,
                "processing_time": processing_time,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        return DenseResult(vectors=all_vecs, processing_time=processing_time)

    @observe(
        name="bge-m3-encode-sparse", as_type="embedding", capture_input=False, capture_output=False
    )
    @bge_retry
    async def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors via /encode/sparse."""
        lf = get_client()
        lf.update_current_span(
            input={
                "texts_count": len(texts),
                "batch_size": self.batch_size,
                "max_length": self.max_length,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        if not texts:
            lf.update_current_span(
                output={"weights_count": 0},
                metadata={"model": BGE_M3_MODEL_NAME},
            )
            return SparseResult(weights=[])
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/encode/sparse",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        all_weights = data["lexical_weights"]
        processing_time = data.get("processing_time")
        lf.update_current_span(
            output={"weights_count": len(all_weights), "processing_time": processing_time},
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        return SparseResult(weights=all_weights, processing_time=processing_time)

    @observe(
        name="bge-m3-encode-hybrid", as_type="embedding", capture_input=False, capture_output=False
    )
    @bge_retry
    async def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse (+ optional ColBERT) via /encode/hybrid (single call)."""
        lf = get_client()
        lf.update_current_span(
            input={
                "texts_count": len(texts),
                "max_length": self.max_length,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        if not texts:
            lf.update_current_span(
                output={"dense_count": 0, "sparse_count": 0, "colbert_count": 0},
                metadata={"model": BGE_M3_MODEL_NAME},
            )
            return HybridResult(dense_vecs=[], lexical_weights=[])
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        result = HybridResult(
            dense_vecs=data["dense_vecs"],
            lexical_weights=data["lexical_weights"],
            colbert_vecs=data.get("colbert_vecs"),
            processing_time=data.get("processing_time"),
        )
        lf.update_current_span(
            output={
                "dense_count": len(result.dense_vecs),
                "dense_dim": len(result.dense_vecs[0]) if result.dense_vecs else 0,
                "sparse_count": len(result.lexical_weights),
                "colbert_count": len(result.colbert_vecs or []),
                "processing_time": result.processing_time,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        return result

    @observe(name="bge-m3-rerank", as_type="embedding", capture_input=False, capture_output=False)
    @bge_retry
    async def rerank(self, query: str, documents: list[str], top_k: int = 5) -> RerankResult:
        """Rerank documents via ColBERT MaxSim /rerank endpoint."""
        lf = get_client()
        lf.update_current_span(
            input={
                "query_length": len(query),
                "documents_count": len(documents),
                "top_k": top_k,
                "max_length": self.max_length,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        if not documents:
            lf.update_current_span(
                output={"results_count": 0, "top_score": None},
                metadata={"model": BGE_M3_MODEL_NAME},
            )
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
        result = RerankResult(
            results=[{"index": r["index"], "score": r["score"]} for r in data["results"]],
            processing_time=data.get("processing_time"),
        )
        lf.update_current_span(
            output={
                "results_count": len(result.results),
                "top_score": result.results[0]["score"] if result.results else None,
                "processing_time": result.processing_time,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        return result

    @observe(
        name="bge-m3-encode-colbert", as_type="embedding", capture_input=False, capture_output=False
    )
    @bge_retry
    async def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors via /encode/colbert."""
        lf = get_client()
        lf.update_current_span(
            input={
                "texts_count": len(texts),
                "max_length": self.max_length,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        if not texts:
            lf.update_current_span(
                output={"colbert_count": 0, "colbert_vector_count": 0},
                metadata={"model": BGE_M3_MODEL_NAME},
            )
            return ColbertResult(colbert_vecs=[])
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/encode/colbert",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        result = ColbertResult(
            colbert_vecs=data["colbert_vecs"],
            processing_time=data.get("processing_time"),
        )
        lf.update_current_span(
            output={
                "colbert_count": len(result.colbert_vecs),
                "colbert_vector_count": len(result.colbert_vecs[0]) if result.colbert_vecs else 0,
                "processing_time": result.processing_time,
            },
            metadata={"model": BGE_M3_MODEL_NAME},
        )
        return result

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
        resp = self._client.post(
            f"{self.base_url}/encode/dense",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return DenseResult(vectors=data["dense_vecs"], processing_time=data.get("processing_time"))

    def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors (sync)."""
        if not texts:
            return SparseResult(weights=[])
        resp = self._client.post(
            f"{self.base_url}/encode/sparse",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return SparseResult(
            weights=data["lexical_weights"], processing_time=data.get("processing_time")
        )

    def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors (sync)."""
        if not texts:
            return ColbertResult(colbert_vecs=[])
        resp = self._client.post(
            f"{self.base_url}/encode/colbert",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return ColbertResult(
            colbert_vecs=data["colbert_vecs"],
            processing_time=data.get("processing_time"),
        )

    def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse + colbert in a single /encode/hybrid call.

        This is 3x more efficient than calling encode_dense + encode_sparse +
        encode_colbert separately, as the BGE-M3 model runs one forward pass.
        """
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        resp = self._client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": texts, "batch_size": self.batch_size, "max_length": self.max_length},
        )
        resp.raise_for_status()
        data = resp.json()
        return HybridResult(
            dense_vecs=data["dense_vecs"],
            lexical_weights=data["lexical_weights"],
            colbert_vecs=data.get("colbert_vecs"),
            processing_time=data.get("processing_time"),
        )

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()
