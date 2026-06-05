"""LangChain Embeddings wrappers for BGE-M3 API (canonical home, #2045).

Moved from ``telegram_bot/integrations/embeddings.py`` as the second slice
of the reverse-layering fix tracked under #1948 / #2045 / #2049. The
legacy ``telegram_bot.integrations.embeddings`` module is kept as a thin
re-export so existing imports across the test suite, ``telegram_bot/``
internals, and external consumers continue to work without churn.

Provides BGEM3Embeddings (dense), BGEM3SparseEmbeddings (sparse), and
BGEM3HybridEmbeddings (dense + sparse + optional ColBERT) that wrap the
local BGE-M3 REST API for use in LangGraph pipelines.

All HTTP communication delegates to BGEM3Client (unified SDK layer).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings

from src.observability import observe
from src.services.bge_m3_client import (
    BGEM3Client,
    ColbertResult,
    DenseResult,
    HybridResult,
    SparseResult,
)


logger = logging.getLogger(__name__)


def _as_list(value: Any) -> Any:
    """Convert numpy/torch-like outputs into plain JSON-compatible lists."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, list):
        return [_as_list(item) for item in value]
    if isinstance(value, tuple):
        return [_as_list(item) for item in value]
    return value


def _normalize_sparse_row(row: dict[Any, Any]) -> dict[str, list[Any]]:
    if "indices" in row and "values" in row:
        return {
            "indices": [int(idx) for idx in row["indices"]],
            "values": [float(value) for value in row["values"]],
        }
    indices: list[int] = []
    values: list[float] = []
    for index, value in row.items():
        indices.append(int(index))
        values.append(float(value))
    return {"indices": indices, "values": values}


class InProcessBgeM3Provider:
    """Async-compatible BGE-M3 provider backed by local FlagEmbedding.

    This is an opt-in Stage 4 spike adapter. It preserves the HTTP
    ``BGEM3Client`` result contracts while leaving the default HTTP runtime
    unchanged.
    """

    def __init__(
        self,
        *,
        model_factory: Any | None = None,
        batch_size: int = 32,
        max_length: int = 512,
    ) -> None:
        self.batch_size = batch_size
        self.max_length = max_length
        self._model_factory = model_factory

    def _get_model(self) -> Any:
        if self._model_factory is not None:
            return self._model_factory()
        from src.models.embedding_model import get_bge_m3_model

        return get_bge_m3_model()

    async def _encode(
        self,
        texts: list[str],
        *,
        return_dense: bool,
        return_sparse: bool,
        return_colbert_vecs: bool,
    ) -> dict[str, Any]:
        model = self._get_model()
        return await asyncio.to_thread(
            model.encode,
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=return_colbert_vecs,
        )

    @observe(
        name="bge-m3-local-encode-dense",
        as_type="embedding",
        capture_input=False,
        capture_output=False,
    )
    async def encode_dense(self, texts: list[str]) -> DenseResult:
        if not texts:
            return DenseResult(vectors=[])
        data = await self._encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return DenseResult(vectors=_as_list(data["dense_vecs"]))

    @observe(
        name="bge-m3-local-encode-sparse",
        as_type="embedding",
        capture_input=False,
        capture_output=False,
    )
    async def encode_sparse(self, texts: list[str]) -> SparseResult:
        if not texts:
            return SparseResult(weights=[])
        data = await self._encode(
            texts,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        weights = [_normalize_sparse_row(row) for row in data["lexical_weights"]]
        return SparseResult(weights=weights)

    @observe(
        name="bge-m3-local-encode-hybrid",
        as_type="embedding",
        capture_input=False,
        capture_output=False,
    )
    async def encode_hybrid(self, texts: list[str]) -> HybridResult:
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[], colbert_vecs=[])
        data = await self._encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )
        return HybridResult(
            dense_vecs=_as_list(data["dense_vecs"]),
            lexical_weights=[_normalize_sparse_row(row) for row in data["lexical_weights"]],
            colbert_vecs=_as_list(data.get("colbert_vecs") or []),
        )

    @observe(
        name="bge-m3-local-encode-colbert",
        as_type="embedding",
        capture_input=False,
        capture_output=False,
    )
    async def encode_colbert(self, texts: list[str]) -> ColbertResult:
        if not texts:
            return ColbertResult(colbert_vecs=[])
        data = await self._encode(
            texts,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )
        return ColbertResult(colbert_vecs=_as_list(data["colbert_vecs"]))

    async def aclose(self) -> None:
        return None


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

    @observe(name="bge-m3-dense-embed", capture_input=False, capture_output=False)
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

    @observe(name="bge-m3-sparse-embed", capture_input=False, capture_output=False)
    async def aembed_query(self, text: str) -> dict[str, Any]:
        result = await self._client.encode_sparse([text])
        return result.weights[0]

    @observe(name="bge-m3-sparse-embed-batch", capture_input=False, capture_output=False)
    async def aembed_documents(self, texts: list[str]) -> list[dict[str, Any]]:
        if not texts:
            return []
        result = await self._client.encode_sparse(texts)
        return result.weights


class BGEM3HybridEmbeddings(Embeddings):
    """Combined dense+sparse(+ColBERT) embedding via BGE-M3 /encode/hybrid.

    Single HTTP call returns dense and sparse vectors, and may also return
    ColBERT token vectors when the endpoint supports it.
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

    @observe(name="bge-m3-dense-query-embed", capture_input=False, capture_output=False)
    async def aembed_dense_query(self, text: str) -> tuple[list[float], float | None]:
        """Embed query text via /encode/dense, returning (dense_vector, processing_time)."""
        result = await self._client.encode_dense([text])
        return result.vectors[0], result.processing_time

    @observe(name="bge-m3-hybrid-embed", capture_input=False, capture_output=False)
    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Embed text via /encode/hybrid, returning (dense, sparse)."""
        result = await self._client.encode_hybrid([text])
        return result.dense_vecs[0], result.lexical_weights[0]

    @observe(name="bge-m3-hybrid-colbert-embed", capture_input=False, capture_output=False)
    async def aembed_hybrid_with_colbert(
        self, text: str
    ) -> tuple[list[float], dict[str, Any], list[list[float]]]:
        """Embed text returning (dense, sparse, colbert_query_vectors).

        Tries to get all three from /encode/hybrid in one call.
        Falls back to separate /encode/colbert if hybrid doesn't return colbert_vecs.
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

    @observe(name="bge-m3-colbert-query-embed", capture_input=False, capture_output=False)
    async def aembed_colbert_query(self, text: str) -> list[list[float]]:
        """Embed text via /encode/colbert, returning query token vectors only."""
        result = await self._client.encode_colbert([text])
        return result.colbert_vecs[0]

    @observe(name="bge-m3-hybrid-embed-batch", capture_input=False, capture_output=False)
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


__all__ = [
    "BGEM3Embeddings",
    "BGEM3HybridEmbeddings",
    "BGEM3SparseEmbeddings",
    "InProcessBgeM3Provider",
]
