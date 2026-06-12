"""Tests for the canonical BGE-M3 embedding adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider
from src.services.bge_m3_client import ColbertResult, DenseResult, HybridResult, SparseResult


@pytest.mark.asyncio
async def test_bge_provider_delegates_dense_documents_to_client() -> None:
    client = AsyncMock()
    client.encode_dense.return_value = DenseResult(vectors=[[0.1], [0.2]], processing_time=0.4)
    provider = BgeM3EmbeddingProvider(client=client)

    assert await provider.embed_texts(["a", "b"]) == [[0.1], [0.2]]
    client.encode_dense.assert_awaited_once_with(["a", "b"])


@pytest.mark.asyncio
async def test_bge_provider_uses_hybrid_colbert_when_available() -> None:
    client = AsyncMock()
    client.encode_hybrid.return_value = HybridResult(
        dense_vecs=[[0.1]],
        lexical_weights=[{"indices": [1], "values": [0.5]}],
        colbert_vecs=[[[0.2, 0.3]]],
    )
    provider = BgeM3EmbeddingProvider(client=client)

    assert await provider.aembed_hybrid_with_colbert("q") == (
        [0.1],
        {"indices": [1], "values": [0.5]},
        [[0.2, 0.3]],
    )
    client.encode_hybrid.assert_awaited_once_with(["q"])
    client.encode_colbert.assert_not_called()


@pytest.mark.asyncio
async def test_bge_provider_falls_back_to_colbert_endpoint_when_hybrid_omits_it() -> None:
    client = AsyncMock()
    client.encode_hybrid.return_value = HybridResult(
        dense_vecs=[[0.1]],
        lexical_weights=[{"indices": [1], "values": [0.5]}],
        colbert_vecs=None,
    )
    client.encode_colbert.return_value = ColbertResult(colbert_vecs=[[[0.9]]])
    provider = BgeM3EmbeddingProvider(client=client)

    assert await provider.aembed_hybrid_with_colbert("q") == (
        [0.1],
        {"indices": [1], "values": [0.5]},
        [[0.9]],
    )
    client.encode_hybrid.assert_awaited_once_with(["q"])
    client.encode_colbert.assert_awaited_once_with(["q"])


@pytest.mark.asyncio
async def test_bge_provider_sparse_helpers_delegate_to_client() -> None:
    client = AsyncMock()
    client.encode_sparse.return_value = SparseResult(weights=[{"indices": [2], "values": [0.8]}])
    provider = BgeM3EmbeddingProvider(client=client)

    assert await provider.aembed_sparse_query("q") == {"indices": [2], "values": [0.8]}
    client.encode_sparse.assert_awaited_once_with(["q"])
