"""Unified HTTP client for BGE-M3 API endpoints.

Single internal SDK layer for all BGE-M3 interactions:
- /encode/dense  — dense embeddings (1024-dim)
- /encode/sparse — sparse embeddings (lexical_weights)
- /encode/hybrid — dense + sparse + ColBERT in one call (completeness-validated, #3373)
- /encode/colbert — ColBERT multivectors
- /rerank        — ColBERT MaxSim reranking

Centralizes: httpx client lifecycle, retry/timeout policy, response parsing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.services._retry import bge_retry


DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
DEFAULT_BATCH_SIZE = 32
DEFAULT_MAX_LENGTH = 512
BGE_M3_MODEL_NAME = "BAAI/bge-m3"
# Hard per-request text bound enforced by the sidecar (ENCODE_MAX_ITEMS): a
# larger encode request is rejected with 422. The client therefore splits any
# input into requests of at most min(configured_batch_size, MAX_REQUEST_TEXTS)
# texts (#3375).
MAX_REQUEST_TEXTS = 64


def _request_chunks(texts: list[str], batch_size: int) -> list[tuple[int, list[str]]]:
    """Split texts into sequential request chunks of at most ``min(batch_size, 64)``.

    The single shared batching helper for the sync and async encode methods
    (#3375). Each chunk carries its global start offset in the original input
    so per-request partial-failure indexes can be mapped back to global
    positions. A non-positive ``batch_size`` is clamped to 1 so chunking
    always makes progress; values above ``MAX_REQUEST_TEXTS`` are capped at
    the sidecar's per-request bound.
    """
    size = max(1, min(batch_size, MAX_REQUEST_TEXTS))
    return [(start, texts[start : start + size]) for start in range(0, len(texts), size)]


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


class BGEHybridResponseError(ValueError):
    """A raw /encode/hybrid response violated the completeness contract (#3373).

    Every hybrid response must carry dense_vecs, lexical_weights, and
    colbert_vecs with exactly one entry per requested text. Missing, empty,
    and cardinality-mismatched families are protocol errors so ingestion
    never receives an incomplete vector set and no partial ingestion can be
    persisted.
    """


def _validate_hybrid_families(parsed: HybridResult, chunk_len: int, offset: int) -> None:
    """Reject incomplete /encode/hybrid responses before callers see them (#3373).

    ``offset`` is the chunk's global start position in the original input
    (#3375), so batched requests report the failing global text range.
    """
    expected = f"expected {chunk_len} entries for global texts [{offset}, {offset + chunk_len})"
    if len(parsed.dense_vecs) != chunk_len:
        raise BGEHybridResponseError(
            f"/encode/hybrid incomplete response: dense_vecs {expected}, "
            f"got {len(parsed.dense_vecs)}"
        )
    if len(parsed.lexical_weights) != chunk_len:
        raise BGEHybridResponseError(
            f"/encode/hybrid incomplete response: lexical_weights {expected}, "
            f"got {len(parsed.lexical_weights)}"
        )
    if parsed.colbert_vecs is None or len(parsed.colbert_vecs) != chunk_len:
        got = "missing" if parsed.colbert_vecs is None else str(len(parsed.colbert_vecs))
        raise BGEHybridResponseError(
            f"/encode/hybrid incomplete response: colbert_vecs {expected}, got {got}"
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
    """Result from /encode/hybrid (dense + sparse + colbert).

    ``colbert_vecs`` is typed optional for the raw-parse layer only; the
    ``encode_hybrid`` methods enforce complete three-family responses and
    raise :class:`BGEHybridResponseError` otherwise (#3373).
    """

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

    @bge_retry
    async def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors via /encode/dense."""
        if not texts:
            return DenseResult(vectors=[])
        client = await self._get_client()
        vectors: list[list[float]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = await client.post(
                f"{self.base_url}/encode/dense",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_dense_response(resp.json())
            vectors.extend(parsed.vectors)
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return DenseResult(
            vectors=vectors, processing_time=total_time, partial_failures=partial_failures
        )

    @bge_retry
    async def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors via /encode/sparse."""
        if not texts:
            return SparseResult(weights=[])
        client = await self._get_client()
        weights: list[dict[str, Any]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = await client.post(
                f"{self.base_url}/encode/sparse",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_sparse_response(resp.json())
            weights.extend(parsed.weights)
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return SparseResult(
            weights=weights, processing_time=total_time, partial_failures=partial_failures
        )

    @bge_retry
    async def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse + colbert via /encode/hybrid.

        One hybrid request per chunk of at most ``min(batch_size, 64)`` texts;
        a single request when the input already fits (#3375). Each raw
        response must be complete — dense_vecs, lexical_weights, and
        colbert_vecs with exactly ``len(chunk)`` entries — and any missing,
        empty, or mismatched family raises :class:`BGEHybridResponseError`
        so callers fail before persisting partial vectors (#3373).
        """
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        client = await self._get_client()
        dense_vecs: list[list[float]] = []
        lexical_weights: list[dict[str, Any]] = []
        colbert_vecs: list[list[list[float]]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = await client.post(
                f"{self.base_url}/encode/hybrid",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_hybrid_response(resp.json())
            _validate_hybrid_families(parsed, len(chunk), offset)
            dense_vecs.extend(parsed.dense_vecs)
            lexical_weights.extend(parsed.lexical_weights)
            colbert_vecs.extend(parsed.colbert_vecs or [])
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return HybridResult(
            dense_vecs=dense_vecs,
            lexical_weights=lexical_weights,
            colbert_vecs=colbert_vecs,
            processing_time=total_time,
            partial_failures=partial_failures,
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
        client = await self._get_client()
        colbert_vecs: list[list[list[float]]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = await client.post(
                f"{self.base_url}/encode/colbert",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_colbert_response(resp.json())
            colbert_vecs.extend(parsed.colbert_vecs)
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return ColbertResult(
            colbert_vecs=colbert_vecs,
            processing_time=total_time,
            partial_failures=partial_failures,
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

    @bge_retry
    def encode_dense(self, texts: list[str]) -> DenseResult:
        """Encode texts to dense vectors (sync)."""
        if not texts:
            return DenseResult(vectors=[])
        vectors: list[list[float]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = self._client.post(
                f"{self.base_url}/encode/dense",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_dense_response(resp.json())
            vectors.extend(parsed.vectors)
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return DenseResult(
            vectors=vectors, processing_time=total_time, partial_failures=partial_failures
        )

    @bge_retry
    def encode_sparse(self, texts: list[str]) -> SparseResult:
        """Encode texts to sparse vectors (sync)."""
        if not texts:
            return SparseResult(weights=[])
        weights: list[dict[str, Any]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = self._client.post(
                f"{self.base_url}/encode/sparse",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_sparse_response(resp.json())
            weights.extend(parsed.weights)
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return SparseResult(
            weights=weights, processing_time=total_time, partial_failures=partial_failures
        )

    @bge_retry
    def encode_colbert(self, texts: list[str]) -> ColbertResult:
        """Encode texts to ColBERT multivectors (sync)."""
        if not texts:
            return ColbertResult(colbert_vecs=[])
        colbert_vecs: list[list[list[float]]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = self._client.post(
                f"{self.base_url}/encode/colbert",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_colbert_response(resp.json())
            colbert_vecs.extend(parsed.colbert_vecs)
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return ColbertResult(
            colbert_vecs=colbert_vecs,
            processing_time=total_time,
            partial_failures=partial_failures,
        )

    @bge_retry
    def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse + colbert via /encode/hybrid.

        This is 3x more efficient than calling encode_dense + encode_sparse +
        encode_colbert separately, as the BGE-M3 model runs one forward pass
        per request. Inputs larger than ``min(batch_size, 64)`` texts are sent
        as sequential hybrid requests and merged in order (#3375). Each raw
        response must be complete — dense_vecs, lexical_weights, and
        colbert_vecs with exactly ``len(chunk)`` entries — and any missing,
        empty, or mismatched family raises :class:`BGEHybridResponseError`
        so ingestion fails before any Qdrant write (#3373).
        """
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        dense_vecs: list[list[float]] = []
        lexical_weights: list[dict[str, Any]] = []
        colbert_vecs: list[list[list[float]]] = []
        partial_failures: list[dict[str, Any]] = []
        total_time: float | None = None
        for offset, chunk in _request_chunks(texts, self.batch_size):
            resp = self._client.post(
                f"{self.base_url}/encode/hybrid",
                json=_build_payload(chunk, self.batch_size, self.max_length),
            )
            resp.raise_for_status()
            parsed = _parse_hybrid_response(resp.json())
            _validate_hybrid_families(parsed, len(chunk), offset)
            dense_vecs.extend(parsed.dense_vecs)
            lexical_weights.extend(parsed.lexical_weights)
            colbert_vecs.extend(parsed.colbert_vecs or [])
            if parsed.processing_time is not None:
                total_time = (total_time or 0.0) + parsed.processing_time
            partial_failures.extend(
                {**failure, "index": failure["index"] + offset}
                for failure in parsed.partial_failures
            )
        return HybridResult(
            dense_vecs=dense_vecs,
            lexical_weights=lexical_weights,
            colbert_vecs=colbert_vecs,
            processing_time=total_time,
            partial_failures=partial_failures,
        )

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> BGEM3SyncClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
