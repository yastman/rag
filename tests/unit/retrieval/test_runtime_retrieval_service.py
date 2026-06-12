"""Tests for the pure runtime retrieval boundary."""

from __future__ import annotations

from typing import Any

import pytest

from src.adapters.embeddings.base import EmbeddingProvider
from src.runtime.retrieval import RetrievalRequest, RetrievalService


class HybridColbertEmbeddings(EmbeddingProvider):
    async def embed_texts(self, texts):  # pragma: no cover - not used in this path
        return [[0.0] for _ in texts]

    async def aembed_hybrid_with_colbert(self, text: str):
        assert text == "hello"
        return [0.1], {"indices": [1], "values": [0.5]}, [[0.2, 0.3]]


class DenseOnlyEmbeddings(EmbeddingProvider):
    async def embed_texts(self, texts):
        return [[0.7] for _ in texts]


class RecordingQdrant:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def hybrid_search_rrf_colbert(self, **kwargs):
        self.calls.append(("colbert", kwargs))
        return [{"id": "colbert"}]

    async def hybrid_search_rrf(self, **kwargs):
        self.calls.append(("rrf", kwargs))
        return [{"id": "rrf"}]


@pytest.mark.asyncio
async def test_retrieve_prefers_hybrid_colbert_provider_path() -> None:
    qdrant = RecordingQdrant()
    service = RetrievalService(embeddings=HybridColbertEmbeddings(), qdrant=qdrant)  # type: ignore[arg-type]

    result = await service.retrieve(
        RetrievalRequest(query="hello", filters={"topic": "docs"}, top_k=3, return_meta=True)
    )

    assert result == [{"id": "colbert"}]
    assert qdrant.calls == [
        (
            "colbert",
            {
                "dense_vector": [0.1],
                "sparse_vector": {"indices": [1], "values": [0.5]},
                "colbert_query": [[0.2, 0.3]],
                "filters": {"topic": "docs"},
                "top_k": 3,
                "return_meta": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_dense_only_rrf_path() -> None:
    qdrant = RecordingQdrant()
    service = RetrievalService(embeddings=DenseOnlyEmbeddings(), qdrant=qdrant)  # type: ignore[arg-type]

    result = await service.retrieve(RetrievalRequest(query="plain"))

    assert result == [{"id": "rrf"}]
    assert qdrant.calls == [
        (
            "rrf",
            {
                "dense_vector": [0.7],
                "sparse_vector": None,
                "filters": None,
                "top_k": 5,
                "return_meta": False,
            },
        )
    ]


class HybridOnlyEmbeddings(EmbeddingProvider):
    async def embed_texts(self, texts):  # pragma: no cover - not used in this path
        return [[0.0] for _ in texts]

    async def aembed_hybrid(self, text: str):
        assert text == "hybrid"
        return [0.4], {"indices": [4], "values": [0.4]}


class ColbertQdrantNotImplemented(RecordingQdrant):
    async def hybrid_search_rrf_colbert(self, **kwargs):
        raise NotImplementedError("qdrant colbert path is misconfigured")


@pytest.mark.asyncio
async def test_retrieve_uses_hybrid_rrf_when_colbert_embedding_is_unavailable() -> None:
    qdrant = RecordingQdrant()
    service = RetrievalService(embeddings=HybridOnlyEmbeddings(), qdrant=qdrant)  # type: ignore[arg-type]

    result = await service.retrieve(RetrievalRequest(query="hybrid", top_k=2))

    assert result == [{"id": "rrf"}]
    assert qdrant.calls == [
        (
            "rrf",
            {
                "dense_vector": [0.4],
                "sparse_vector": {"indices": [4], "values": [0.4]},
                "filters": None,
                "top_k": 2,
                "return_meta": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_retrieve_does_not_swallow_qdrant_not_implemented_errors() -> None:
    service = RetrievalService(
        embeddings=HybridColbertEmbeddings(),
        qdrant=ColbertQdrantNotImplemented(),  # type: ignore[arg-type]
    )

    with pytest.raises(NotImplementedError, match="qdrant colbert path"):
        await service.retrieve(RetrievalRequest(query="hello"))
