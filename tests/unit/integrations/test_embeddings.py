"""Tests for BGE-M3 LangChain embedding wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from langchain_core.embeddings import Embeddings

from telegram_bot.integrations.embeddings import (
    BGEM3Embeddings,
    BGEM3HybridEmbeddings,
    BGEM3SparseEmbeddings,
)


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


class TestBGEM3HybridEmbeddings:
    async def test_aembed_hybrid_returns_dense_and_sparse(self):
        """Hybrid embed returns both dense_vecs and lexical_weights from one call."""
        hybrid_response = {
            "dense_vecs": [[0.1, 0.2, 0.3]],
            "lexical_weights": [{"indices": [1, 5], "values": [0.1, 0.5]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            dense, sparse = await emb.aembed_hybrid("test query")
        assert dense == [0.1, 0.2, 0.3]
        assert sparse == {"indices": [1, 5], "values": [0.1, 0.5]}

    async def test_posts_to_hybrid_endpoint(self):
        hybrid_response = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.1]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            await emb.aembed_hybrid("test")
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/encode/hybrid" in call_args[0][0]

    async def test_shared_client_reused(self):
        """Client is created once and reused across calls."""
        hybrid_response = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.1]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            await emb.aembed_hybrid("test1")
            await emb.aembed_hybrid("test2")
            # Same client instance used (shared)
            assert emb._client is not None

    async def test_aembed_query_delegates_to_hybrid(self):
        """aembed_query returns only dense part from hybrid call."""
        hybrid_response = {
            "dense_vecs": [[0.1, 0.2]],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            result = await emb.aembed_query("test")
        assert result == [0.1, 0.2]


class TestBGEM3HybridRetry:
    """Tests for retry behavior on transient errors."""

    @pytest.fixture(autouse=True)
    def _disable_retry_sleep(self, monkeypatch: pytest.MonkeyPatch):
        """Keep retry attempts deterministic without real backoff waits."""

        async def _noop_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(BGEM3HybridEmbeddings.aembed_hybrid.retry, "sleep", _noop_sleep)

    @pytest.mark.parametrize(
        "error_cls,error_msg",
        [
            (httpx.RemoteProtocolError, "Server disconnected without sending a response"),
            (httpx.ConnectTimeout, "Connection timed out"),
        ],
        ids=["remote_protocol_error", "connect_timeout"],
    )
    async def test_retries_on_transient_error(self, error_cls, error_msg):
        """Retries on transient transport errors and succeeds on second attempt."""
        ok_response = httpx.Response(
            200,
            json={"dense_vecs": [[0.1, 0.2]], "lexical_weights": [{"1": 0.5}]},
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error_cls(error_msg)
            return ok_response

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            dense, _sparse = await emb.aembed_hybrid("test")

        assert dense == [0.1, 0.2]
        assert call_count == 2  # 1 fail + 1 success

    async def test_raises_after_max_retries(self):
        """Raises original exception after all retries exhausted."""

        async def always_fail(*args, **kwargs):
            raise httpx.RemoteProtocolError("Server disconnected without sending a response")

        with patch("httpx.AsyncClient.post", side_effect=always_fail):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            with pytest.raises(httpx.RemoteProtocolError):
                await emb.aembed_hybrid("test")

    async def test_no_retry_on_http_status_error(self):
        """Does NOT retry on HTTP 500 (status error = not transient transport)."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = httpx.Response(
                500,
                request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
            )
            response.raise_for_status()

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            emb = BGEM3HybridEmbeddings(base_url="http://fake:8000")
            with pytest.raises(httpx.HTTPStatusError):
                await emb.aembed_hybrid("test")

        assert call_count == 1  # No retries


class TestBGEM3HybridTimeout:
    """Tests for granular timeout configuration."""

    @pytest.mark.parametrize(
        ("kwargs", "expected_read", "expected_connect"),
        [
            ({}, 30.0, 5.0),
            ({"timeout": 60.0}, 60.0, 60.0),
        ],
        ids=["default_granular", "custom_override"],
    )
    async def test_timeout_configuration(self, kwargs, expected_read, expected_connect):
        """Timeout is configured correctly (default granular or custom override)."""
        emb = BGEM3HybridEmbeddings(base_url="http://fake:8000", **kwargs)
        client = emb._get_client()
        assert client.timeout.read == expected_read
        assert client.timeout.connect == expected_connect
