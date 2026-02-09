"""Tests for BGE-M3 LangChain embedding wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.embeddings import Embeddings

from telegram_bot.integrations.embeddings import BGEM3Embeddings, BGEM3SparseEmbeddings


class TestBGEM3Embeddings:
    def test_inherits_from_embeddings(self):
        emb = BGEM3Embeddings(base_url="http://fake:8000")
        assert isinstance(emb, Embeddings)

    async def test_aembed_query(self):
        mock_response = httpx.Response(
            200,
            json={"dense_vecs": [[0.1, 0.2, 0.3]]},
            request=httpx.Request("POST", "http://fake:8000/encode/dense"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3Embeddings(base_url="http://fake:8000")
            result = await emb.aembed_query("test query")
        assert result == [0.1, 0.2, 0.3]

    async def test_aembed_documents(self):
        mock_response = httpx.Response(
            200,
            json={"dense_vecs": [[0.1, 0.2], [0.3, 0.4]]},
            request=httpx.Request("POST", "http://fake:8000/encode/dense"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3Embeddings(base_url="http://fake:8000")
            result = await emb.aembed_documents(["doc1", "doc2"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    async def test_aembed_documents_empty(self):
        emb = BGEM3Embeddings(base_url="http://fake:8000")
        result = await emb.aembed_documents([])
        assert result == []

    async def test_posts_to_correct_endpoint(self):
        mock_response = httpx.Response(
            200,
            json={"dense_vecs": [[0.1]]},
            request=httpx.Request("POST", "http://fake:8000/encode/dense"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            emb = BGEM3Embeddings(base_url="http://fake:8000")
            await emb.aembed_query("test")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/encode/dense" in call_args[0][0]

    async def test_batching(self):
        """Test that documents are batched correctly."""
        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            n = len(json["texts"])
            return httpx.Response(
                200,
                json={"dense_vecs": [[0.1] * 3 for _ in range(n)]},
                request=httpx.Request("POST", url),
            )

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            emb = BGEM3Embeddings(base_url="http://fake:8000", batch_size=2)
            result = await emb.aembed_documents(["a", "b", "c"])

        assert len(result) == 3
        assert call_count == 2  # 2 texts + 1 text


class TestBGEM3SparseEmbeddings:
    async def test_aembed_query(self):
        sparse_vec = {"indices": [1, 5, 10], "values": [0.1, 0.5, 0.9]}
        mock_response = httpx.Response(
            200,
            json={"lexical_weights": [sparse_vec]},
            request=httpx.Request("POST", "http://fake:8000/encode/sparse"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3SparseEmbeddings(base_url="http://fake:8000")
            result = await emb.aembed_query("test query")
        assert result == sparse_vec

    async def test_aembed_documents(self):
        lexical_weights = [
            {"indices": [1], "values": [0.1]},
            {"indices": [2], "values": [0.2]},
        ]
        mock_response = httpx.Response(
            200,
            json={"lexical_weights": lexical_weights},
            request=httpx.Request("POST", "http://fake:8000/encode/sparse"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3SparseEmbeddings(base_url="http://fake:8000")
            result = await emb.aembed_documents(["doc1", "doc2"])
        assert result == lexical_weights

    async def test_aembed_documents_empty(self):
        emb = BGEM3SparseEmbeddings(base_url="http://fake:8000")
        result = await emb.aembed_documents([])
        assert result == []

    async def test_posts_to_sparse_endpoint(self):
        sparse_vec = {"indices": [1], "values": [0.5]}
        mock_response = httpx.Response(
            200,
            json={"lexical_weights": [sparse_vec]},
            request=httpx.Request("POST", "http://fake:8000/encode/sparse"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            emb = BGEM3SparseEmbeddings(base_url="http://fake:8000")
            await emb.aembed_query("test")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/encode/sparse" in call_args[0][0]
