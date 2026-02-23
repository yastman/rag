"""Unit tests for BGEM3Client — unified BGE-M3 SDK layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


@pytest.fixture
def client():
    from telegram_bot.services.bge_m3_client import BGEM3Client

    return BGEM3Client(base_url="http://localhost:8000")


@pytest.fixture
def sync_client():
    from telegram_bot.services.bge_m3_client import BGEM3SyncClient

    return BGEM3SyncClient(base_url="http://localhost:8000")


class TestBGEM3Client:
    """Tests for async BGEM3Client."""

    async def test_encode_dense_returns_vectors(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024, [0.2] * 1024],
            "processing_time": 0.05,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_dense(["hello", "world"])

        assert len(result.vectors) == 2
        assert len(result.vectors[0]) == 1024
        assert result.processing_time == 0.05
        mock_http.post.assert_called_once()
        assert "/encode/dense" in mock_http.post.call_args[0][0]

    async def test_encode_dense_empty_input(self, client):
        result = await client.encode_dense([])
        assert result.vectors == []

    async def test_encode_sparse_returns_weights(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "lexical_weights": [{"indices": [1, 2], "values": [0.5, 0.3]}],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_sparse(["hello"])

        assert len(result.weights) == 1
        assert "indices" in result.weights[0]
        assert "/encode/sparse" in mock_http.post.call_args[0][0]

    async def test_encode_sparse_empty_input(self, client):
        result = await client.encode_sparse([])
        assert result.weights == []

    async def test_encode_hybrid_returns_both(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
            "processing_time": 0.1,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_hybrid(["hello"])

        assert len(result.dense_vecs) == 1
        assert len(result.lexical_weights) == 1
        assert result.processing_time == 0.1
        assert "/encode/hybrid" in mock_http.post.call_args[0][0]

    async def test_encode_hybrid_empty_input(self, client):
        result = await client.encode_hybrid([])
        assert result.dense_vecs == []
        assert result.lexical_weights == []

    async def test_rerank_returns_results(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"index": 0, "score": 0.95},
                {"index": 1, "score": 0.80},
            ],
            "processing_time": 0.2,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.rerank("query", ["doc1", "doc2"], top_k=2)

        assert len(result.results) == 2
        assert result.results[0]["score"] == 0.95
        assert result.processing_time == 0.2
        assert "/rerank" in mock_http.post.call_args[0][0]

    async def test_rerank_empty_documents(self, client):
        result = await client.rerank("query", [])
        assert result.results == []

    async def test_health_returns_true(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        assert await client.health() is True

    async def test_health_returns_false_on_error(self, client):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_http.is_closed = False
        client._client = mock_http

        assert await client.health() is False

    async def test_aclose(self, client):
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        client._client = mock_http

        await client.aclose()
        mock_http.aclose.assert_called_once()

    async def test_encode_colbert_returns_vectors(self, client):
        """Test ColBERT encoding returns nested list of token vectors."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # ColBERT: list of texts -> list of (num_tokens, 1024) arrays
        # Single text with 3 tokens, each 1024-dim
        mock_resp.json.return_value = {
            "colbert_vecs": [[[0.1] * 1024] * 3],
            "processing_time": 0.05,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_colbert(["hello"])

        assert len(result.colbert_vecs) == 1
        assert len(result.colbert_vecs[0]) == 3  # 3 tokens
        assert len(result.colbert_vecs[0][0]) == 1024  # 1024-dim per token
        assert result.processing_time == 0.05
        mock_http.post.assert_called_once()
        assert "/encode/colbert" in mock_http.post.call_args[0][0]

    async def test_encode_colbert_empty_input(self, client):
        result = await client.encode_colbert([])
        assert result.colbert_vecs == []

    async def test_encode_hybrid_includes_colbert_vecs(self, client):
        """encode_hybrid returns colbert_vecs when present in response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
            "colbert_vecs": [[[0.2] * 1024] * 4],  # 1 text, 4 tokens
            "processing_time": 0.1,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_hybrid(["hello"])

        assert result.colbert_vecs is not None
        assert len(result.colbert_vecs) == 1
        assert len(result.colbert_vecs[0]) == 4

    async def test_encode_hybrid_colbert_vecs_optional(self, client):
        """encode_hybrid works when response has no colbert_vecs (backward compat)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
            "processing_time": 0.1,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_hybrid(["hello"])

        assert result.colbert_vecs is None
        # Existing fields still work
        assert len(result.dense_vecs) == 1
        assert len(result.lexical_weights) == 1

    async def test_encode_dense_batching(self, client):
        """Large input gets split into batches."""
        from telegram_bot.services.bge_m3_client import BGEM3Client

        small_client = BGEM3Client(base_url="http://localhost:8000", batch_size=2)

        call_count = 0

        async def mock_post(url, json=None):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            n = len(json["texts"])
            resp.json.return_value = {"dense_vecs": [[0.1] * 1024] * n}
            return resp

        mock_http = AsyncMock()
        mock_http.post = mock_post
        mock_http.is_closed = False
        small_client._client = mock_http

        result = await small_client.encode_dense(["a", "b", "c", "d", "e"])

        assert len(result.vectors) == 5
        assert call_count == 3  # ceil(5/2) = 3 batches


class TestBGEM3SyncClient:
    """Tests for synchronous BGEM3SyncClient."""

    def test_encode_dense_sync(self, sync_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"dense_vecs": [[0.1] * 1024]}

        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(return_value=mock_resp)

        result = sync_client.encode_dense(["hello"])

        assert len(result.vectors) == 1
        assert "/encode/dense" in sync_client._client.post.call_args[0][0]

    def test_encode_sparse_sync(self, sync_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"lexical_weights": [{"indices": [1], "values": [0.5]}]}

        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(return_value=mock_resp)

        result = sync_client.encode_sparse(["hello"])

        assert len(result.weights) == 1
        assert "/encode/sparse" in sync_client._client.post.call_args[0][0]

    def test_encode_dense_empty(self, sync_client):
        result = sync_client.encode_dense([])
        assert result.vectors == []

    def test_encode_sparse_empty(self, sync_client):
        result = sync_client.encode_sparse([])
        assert result.weights == []

    def test_encode_colbert_sync_returns_multivectors(self, sync_client):
        """encode_colbert returns ColbertResult with nested token vectors."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # 1 text, 3 tokens, 1024-dim each
        mock_resp.json.return_value = {
            "colbert_vecs": [[[0.1] * 1024] * 3],
            "processing_time": 0.05,
        }

        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(return_value=mock_resp)

        result = sync_client.encode_colbert(["hello world"])

        assert len(result.colbert_vecs) == 1
        assert len(result.colbert_vecs[0]) == 3
        assert len(result.colbert_vecs[0][0]) == 1024
        assert result.processing_time == 0.05
        assert "/encode/colbert" in sync_client._client.post.call_args[0][0]

    def test_encode_colbert_sync_empty_input(self, sync_client):
        """encode_colbert returns empty result for empty input (no HTTP call)."""
        result = sync_client.encode_colbert([])
        assert result.colbert_vecs == []
