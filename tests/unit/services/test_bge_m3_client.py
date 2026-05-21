"""Unit tests for BGEM3Client — unified BGE-M3 SDK layer."""

from __future__ import annotations

from unittest import mock
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

    async def test_encode_sparse_contract_rejects_legacy_sparse_vecs_key(self, client):
        """Contract test: /encode/sparse must return lexical_weights (not sparse_vecs)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "sparse_vecs": [{"indices": [1, 2], "values": [0.5, 0.3]}],
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(KeyError):
            await client.encode_sparse(["hello"])

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

    async def test_encode_hybrid_contract_requires_dense_and_lexical_keys(self, client):
        """Contract test: /encode/hybrid response must contain both required keys."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            # lexical_weights intentionally missing
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(KeyError):
            await client.encode_hybrid(["hello"])

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
        """batch_size is passed as server hint in a single request."""
        from telegram_bot.services.bge_m3_client import BGEM3Client

        small_client = BGEM3Client(base_url="http://localhost:8000", batch_size=2)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"dense_vecs": [[0.1] * 1024] * 5}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        small_client._client = mock_http

        result = await small_client.encode_dense(["a", "b", "c", "d", "e"])

        assert len(result.vectors) == 5
        mock_http.post.assert_called_once()
        call_json = mock_http.post.call_args[1]["json"]
        assert call_json["texts"] == ["a", "b", "c", "d", "e"]
        assert call_json["batch_size"] == 2


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

    def test_encode_hybrid_returns_hybrid_result(self, sync_client):
        """Single /encode/hybrid call returns dense + sparse + colbert."""
        with mock.patch.object(sync_client._client, "post") as mock_post:
            mock_post.return_value = mock.MagicMock(
                status_code=200,
                json=lambda: {
                    "dense_vecs": [[0.1] * 1024],
                    "lexical_weights": [{"indices": [1, 2], "values": [0.5, 0.3]}],
                    "colbert_vecs": [[[0.1] * 1024] * 5],
                    "processing_time": 0.42,
                },
                raise_for_status=lambda: None,
            )
            result = sync_client.encode_hybrid(["hello"])

            assert len(result.dense_vecs) == 1
            assert len(result.lexical_weights) == 1
            assert result.colbert_vecs is not None
            assert len(result.colbert_vecs) == 1
            assert result.processing_time == 0.42
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "/encode/hybrid" in call_url

    def test_encode_hybrid_empty_input(self, sync_client):
        """Empty input returns empty HybridResult without HTTP call."""
        result = sync_client.encode_hybrid([])
        assert result.dense_vecs == []
        assert result.lexical_weights == []

    def test_encode_hybrid_http_error_raises(self, sync_client):
        """HTTP 500 raises HTTPStatusError."""
        with mock.patch.object(sync_client._client, "post") as mock_post:
            mock_post.return_value = mock.MagicMock()
            mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error", request=mock.MagicMock(), response=mock.MagicMock(status_code=500)
            )
            with pytest.raises(httpx.HTTPStatusError):
                sync_client.encode_hybrid(["hello"])

    def test_encode_hybrid_batches_large_input(self, sync_client):
        """batch_size is passed as server hint in a single request."""
        sync_client.batch_size = 2
        texts = ["a", "b", "c"]

        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024] * 3,
            "lexical_weights": [{"indices": [1], "values": [0.5]}] * 3,
            "colbert_vecs": [[[0.1] * 1024] * 5] * 3,
            "processing_time": 0.1,
        }
        mock_resp.raise_for_status = lambda: None

        with mock.patch.object(sync_client._client, "post", return_value=mock_resp) as mock_post:
            result = sync_client.encode_hybrid(texts)

        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["texts"] == ["a", "b", "c"]
        assert call_json["batch_size"] == 2
        assert len(result.dense_vecs) == 3
        assert len(result.lexical_weights) == 3
        assert len(result.colbert_vecs) == 3


class TestBGEM3ClientReconnectRace:
    """Reconnect race-condition contract for _get_client (#1641).

    Goal: under concurrent reconnect (multiple tasks hitting _get_client when
    self._client is None or closed), only ONE new httpx.AsyncClient must be
    constructed, and any old non-closed client must be closed exactly once.

    These tests use the real asyncio scheduler with multiple awaited tasks.
    httpx.AsyncClient is patched at module level so we can count instantiations
    without performing real I/O.
    """

    async def test_concurrent_first_call_creates_only_one_async_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """N concurrent first-time _get_client() callers => 1 AsyncClient construction."""
        import asyncio

        from src.services import bge_m3_client as mod

        instances: list[MagicMock] = []

        def fake_async_client(*args: object, **kwargs: object) -> MagicMock:
            inst = MagicMock()
            inst.is_closed = False
            inst.aclose = AsyncMock()
            instances.append(inst)
            return inst

        monkeypatch.setattr(mod.httpx, "AsyncClient", fake_async_client)

        client = mod.BGEM3Client(base_url="http://localhost:8000")

        # Force a yield point inside _get_client so concurrent tasks observe
        # the same self._client is None state before any of them assigns.
        async def call_get_client() -> object:
            return await client._get_client()

        results = await asyncio.gather(*(call_get_client() for _ in range(8)))

        assert len(instances) == 1, (
            f"Expected exactly 1 AsyncClient instantiation, got {len(instances)}"
        )
        assert all(r is instances[0] for r in results)

    async def test_concurrent_reconnect_after_close_creates_only_one_new_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When existing client is closed, concurrent reconnects produce 1 replacement."""
        import asyncio

        from src.services import bge_m3_client as mod

        instances: list[MagicMock] = []

        def fake_async_client(*args: object, **kwargs: object) -> MagicMock:
            inst = MagicMock()
            inst.is_closed = False
            inst.aclose = AsyncMock()
            instances.append(inst)
            return inst

        monkeypatch.setattr(mod.httpx, "AsyncClient", fake_async_client)

        client = mod.BGEM3Client(base_url="http://localhost:8000")

        # Pre-seed a closed client so reconnect path triggers.
        closed = MagicMock()
        closed.is_closed = True
        closed.aclose = AsyncMock()
        client._client = closed

        async def call_get_client() -> object:
            return await client._get_client()

        results = await asyncio.gather(*(call_get_client() for _ in range(8)))

        assert len(instances) == 1, (
            f"Expected exactly 1 replacement AsyncClient, got {len(instances)}"
        )
        assert all(r is instances[0] for r in results)
        # A pre-closed client must NOT be aclose()'d again (already closed).
        closed.aclose.assert_not_awaited()

    async def test_get_client_returns_existing_open_client_without_replacement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If self._client is open, _get_client must return it as-is (no new instance)."""
        from src.services import bge_m3_client as mod

        instances: list[MagicMock] = []

        def fake_async_client(*args: object, **kwargs: object) -> MagicMock:
            inst = MagicMock()
            inst.is_closed = False
            instances.append(inst)
            return inst

        monkeypatch.setattr(mod.httpx, "AsyncClient", fake_async_client)

        client = mod.BGEM3Client(base_url="http://localhost:8000")
        existing = MagicMock()
        existing.is_closed = False
        client._client = existing

        result = await client._get_client()

        assert result is existing
        assert instances == []  # no new construction

    async def test_aclose_concurrent_with_get_client_does_not_double_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """aclose() racing with _get_client() must not aclose() the same client twice."""
        from src.services import bge_m3_client as mod

        instances: list[MagicMock] = []

        def fake_async_client(*args: object, **kwargs: object) -> MagicMock:
            inst = MagicMock()
            inst.is_closed = False
            inst.aclose = AsyncMock()
            instances.append(inst)
            return inst

        monkeypatch.setattr(mod.httpx, "AsyncClient", fake_async_client)

        client = mod.BGEM3Client(base_url="http://localhost:8000")

        # Establish initial client.
        first = await client._get_client()
        assert first is instances[0]

        # Close it; concurrent _get_client must observe is_closed and replace.
        await client.aclose()
        first.aclose.assert_awaited_once()

        second = await client._get_client()
        assert second is not first
        # Original closed client never aclose()'d twice.
        first.aclose.assert_awaited_once()
