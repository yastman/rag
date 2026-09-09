"""Unit tests for BGEM3Client — unified BGE-M3 SDK layer."""

from __future__ import annotations

import asyncio
import time
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


# Pure-mock tests — no Docker / network. Marked so the core `no_services` gate
# (`-m 'no_services and not requires_extras and not slow'`) actually runs them.
pytestmark = pytest.mark.no_services


@pytest.fixture(autouse=True)
def _instant_retry_backoff(monkeypatch):
    """Neutralise tenacity's exponential back-off so retry tests are instant.

    bge_retry now retries 429/503/5xx and transport errors; without this the
    HTTP-error and timeout tests would each sleep through the real back-off.
    tenacity resolves its sleep fn at call time (``time.sleep`` for sync,
    ``asyncio.sleep`` for async), so patching the module attrs zeroes the wait
    for both paths.
    """

    async def _no_async_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(asyncio, "sleep", _no_async_sleep)


@pytest.fixture
def client():
    from src.services.bge_m3_client import BGEM3Client

    return BGEM3Client(base_url="http://localhost:8000")


@pytest.fixture
def sync_client():
    from src.services.bge_m3_client import BGEM3SyncClient

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
        """batch_size is applied client-side (#3375): 5 texts at batch_size=2 → requests of 2,2,1."""
        from src.services.bge_m3_client import BGEM3Client

        small_client = BGEM3Client(base_url="http://localhost:8000", batch_size=2)
        texts = ["t0", "t1", "t2", "t3", "t4"]
        captured_sizes: list[int] = []

        def _post(url, json=None, **_kwargs):
            captured_sizes.append(len(json["texts"]))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "dense_vecs": [[float(t[1:])] * 1024 for t in json["texts"]],
                "processing_time": 0.05,
            }
            return mock_resp

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=_post)
        mock_http.is_closed = False
        small_client._client = mock_http

        result = await small_client.encode_dense(texts)

        assert captured_sizes == [2, 2, 1]
        assert len(result.vectors) == 5
        assert [int(v[0]) for v in result.vectors] == [0, 1, 2, 3, 4]
        call_json = mock_http.post.call_args[1]["json"]
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
        """batch_size is applied client-side (#3375): 3 texts at batch_size=2 → requests of 2,1."""
        sync_client.batch_size = 2
        texts = ["t0", "t1", "t2"]
        captured_sizes: list[int] = []

        def _post(url, json=None, **_kwargs):
            captured_sizes.append(len(json["texts"]))
            chunk = json["texts"]
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = lambda: None
            mock_resp.json.return_value = {
                "dense_vecs": [[float(t[1:])] * 1024 for t in chunk],
                "lexical_weights": [{"indices": [int(t[1:])], "values": [1.0]} for t in chunk],
                "colbert_vecs": [[[float(t[1:])] * 1024] for t in chunk],
                "processing_time": 0.1,
            }
            return mock_resp

        with mock.patch.object(sync_client._client, "post", side_effect=_post):
            result = sync_client.encode_hybrid(texts)

        assert captured_sizes == [2, 1]
        assert len(result.dense_vecs) == 3
        assert len(result.lexical_weights) == 3
        assert len(result.colbert_vecs) == 3
        assert [int(v[0]) for v in result.dense_vecs] == [0, 1, 2]


class TestSharedParseHelpers:
    """Tests for module-level _build_payload and _parse_* helpers."""

    def test_build_payload_includes_all_fields(self):
        from src.services.bge_m3_client import _build_payload

        payload = _build_payload(["a", "b"], batch_size=8, max_length=256)
        assert payload == {"texts": ["a", "b"], "batch_size": 8, "max_length": 256}

    def test_parse_dense_response(self):
        from src.services.bge_m3_client import DenseResult, _parse_dense_response

        data = {"dense_vecs": [[0.1] * 1024, [0.2] * 1024], "processing_time": 0.05}
        result = _parse_dense_response(data)
        assert isinstance(result, DenseResult)
        assert len(result.vectors) == 2
        assert result.processing_time == 0.05

    def test_parse_dense_response_missing_processing_time(self):
        from src.services.bge_m3_client import _parse_dense_response

        result = _parse_dense_response({"dense_vecs": [[0.1] * 1024]})
        assert result.processing_time is None

    def test_parse_sparse_response(self):
        from src.services.bge_m3_client import SparseResult, _parse_sparse_response

        data = {"lexical_weights": [{"indices": [1, 2], "values": [0.5, 0.3]}]}
        result = _parse_sparse_response(data)
        assert isinstance(result, SparseResult)
        assert len(result.weights) == 1
        assert result.weights[0]["indices"] == [1, 2]

    def test_parse_colbert_response(self):
        from src.services.bge_m3_client import ColbertResult, _parse_colbert_response

        data = {"colbert_vecs": [[[0.1] * 1024] * 3], "processing_time": 0.07}
        result = _parse_colbert_response(data)
        assert isinstance(result, ColbertResult)
        assert len(result.colbert_vecs) == 1
        assert len(result.colbert_vecs[0]) == 3
        assert result.processing_time == 0.07

    def test_parse_hybrid_response_with_colbert(self):
        from src.services.bge_m3_client import HybridResult, _parse_hybrid_response

        data = {
            "dense_vecs": [[0.1] * 1024],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
            "colbert_vecs": [[[0.2] * 1024] * 4],
            "processing_time": 0.1,
        }
        result = _parse_hybrid_response(data)
        assert isinstance(result, HybridResult)
        assert len(result.dense_vecs) == 1
        assert len(result.lexical_weights) == 1
        assert result.colbert_vecs is not None
        assert len(result.colbert_vecs[0]) == 4
        assert result.processing_time == 0.1

    def test_parse_hybrid_response_without_colbert(self):
        from src.services.bge_m3_client import _parse_hybrid_response

        data = {
            "dense_vecs": [[0.1] * 1024],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
        }
        result = _parse_hybrid_response(data)
        assert result.colbert_vecs is None


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


# ── New coverage: shape, rerank sort order, error/timeout handling ─────────────


class TestEncodeShapes:
    """Shape and dtype contracts for all four encode endpoints (mock httpx)."""

    async def test_encode_dense_shape_1x1024(self, client) -> None:
        """/encode/dense returns vectors with shape (1, 1024) and float values."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            "processing_time": 0.01,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_dense(["hello"])

        assert len(result.vectors) == 1, "expected 1 vector for 1 input text"
        assert len(result.vectors[0]) == 1024, "dense vector must be 1024-dim"
        assert all(isinstance(v, float) for v in result.vectors[0]), "all values must be float"

    async def test_encode_sparse_bm42_format(self, client) -> None:
        """/encode/sparse returns BM42-style {indices, values} dict per text."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "lexical_weights": [{"indices": [5, 42, 101], "values": [0.7, 0.3, 0.9]}],
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_sparse(["hello"])

        assert len(result.weights) == 1
        w = result.weights[0]
        assert "indices" in w, "sparse weight must have 'indices' key (BM42 format)"
        assert "values" in w, "sparse weight must have 'values' key (BM42 format)"
        assert len(w["indices"]) == len(w["values"]), "indices/values lengths must match"
        assert all(isinstance(i, int) for i in w["indices"]), "indices must be ints"
        assert all(isinstance(v, float) for v in w["values"]), "values must be floats"

    async def test_encode_hybrid_returns_dense_and_sparse(self, client) -> None:
        """/encode/hybrid response includes both dense_vecs and lexical_weights."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "dense_vecs": [[0.2] * 1024],
            "lexical_weights": [{"indices": [1, 2], "values": [0.5, 0.3]}],
            "processing_time": 0.05,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_hybrid(["hello"])

        assert len(result.dense_vecs) == 1, "hybrid must include dense_vecs"
        assert len(result.dense_vecs[0]) == 1024, "dense vector must be 1024-dim"
        assert len(result.lexical_weights) == 1, "hybrid must include lexical_weights"
        assert "indices" in result.lexical_weights[0]

    async def test_encode_colbert_multivector_each_1024_dim(self, client) -> None:
        """/encode/colbert returns list-of-token-vecs; each token vec is 1024-dim."""
        # 1 text, 5 tokens, each 1024-dim (typical ColBERT output).
        token_vec = [0.1] * 1024
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "colbert_vecs": [[token_vec] * 5],
            "processing_time": 0.08,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_colbert(["hello world foo bar baz"])

        assert isinstance(result.colbert_vecs, list)
        assert len(result.colbert_vecs) == 1
        token_vecs = result.colbert_vecs[0]
        assert isinstance(token_vecs, list), "colbert output must be list-of-token-vecs"
        assert len(token_vecs) == 5
        for i, vec in enumerate(token_vecs):
            assert len(vec) == 1024, f"token_vecs[{i}] must be 1024-dim"


class TestRerankSortOrder:
    """Rerank endpoint must return results sorted by score descending."""

    async def test_rerank_sorted_by_score_descending(self, client) -> None:
        """rerank() returns results ordered by score high→low."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # Sidecar returns already-sorted results (contract: desc order)
        mock_resp.json.return_value = {
            "results": [
                {"index": 2, "score": 0.95},
                {"index": 0, "score": 0.72},
                {"index": 1, "score": 0.41},
            ],
            "processing_time": 0.15,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        docs = ["doc_zero", "doc_one", "doc_two"]
        result = await client.rerank("my query", docs, top_k=3)

        assert len(result.results) == 3
        scores = [r["score"] for r in result.results]
        assert scores == sorted(scores, reverse=True), (
            f"rerank results must be descending by score, got: {scores}"
        )
        # Top result is the highest-scoring doc (index 2)
        assert result.results[0]["index"] == 2
        assert result.results[0]["score"] == pytest.approx(0.95)

    async def test_rerank_top_k_limits_results(self, client) -> None:
        """rerank() with top_k=2 returns at most 2 results."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"index": 1, "score": 0.88},
                {"index": 0, "score": 0.55},
            ],
            "processing_time": 0.1,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.rerank("query", ["a", "b", "c"], top_k=2)

        assert len(result.results) == 2
        call_json = mock_http.post.call_args[1]["json"]
        assert call_json["top_k"] == 2


class TestErrorAndTimeoutHandling:
    """Client must handle HTTP 500 and timeout gracefully (no hang, typed error)."""

    async def test_encode_dense_http500_raises_http_status_error(self, client) -> None:
        """HTTP 500 from sidecar raises httpx.HTTPStatusError (not swallowed)."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(httpx.HTTPStatusError):
            await client.encode_dense(["hello"])

    async def test_encode_sparse_http500_raises(self, client) -> None:
        """HTTP 500 from /encode/sparse raises HTTPStatusError."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(httpx.HTTPStatusError):
            await client.encode_sparse(["hello"])

    async def test_encode_colbert_http500_raises(self, client) -> None:
        """HTTP 500 from /encode/colbert raises HTTPStatusError."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(httpx.HTTPStatusError):
            await client.encode_colbert(["hello"])

    async def test_rerank_http500_raises(self, client) -> None:
        """HTTP 500 from /rerank raises HTTPStatusError."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(httpx.HTTPStatusError):
            await client.rerank("query", ["doc1"])

    async def test_encode_dense_read_timeout_raises(self, client) -> None:
        """ReadTimeout from sidecar raises httpx.ReadTimeout (does not hang)."""
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ReadTimeout("timed out", request=MagicMock()))
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(httpx.ReadTimeout):
            await client.encode_dense(["hello"])

    async def test_encode_hybrid_connect_timeout_raises(self, client) -> None:
        """ConnectTimeout (sidecar unreachable) raises httpx.ConnectTimeout."""
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            side_effect=httpx.ConnectTimeout("connect timed out", request=MagicMock())
        )
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(httpx.ConnectTimeout):
            await client.encode_hybrid(["hello"])


# ── Retry policy: bge_retry must retry 429/503 for sync + async (card_7cc460feaec0) ──


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        f"status {status_code}",
        request=MagicMock(),
        response=MagicMock(status_code=status_code),
    )


def _failing_resp(status_code: int) -> MagicMock:
    """Response mock whose raise_for_status() raises HTTPStatusError(status_code)."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = _http_status_error(status_code)
    return resp


def _dense_ok_resp() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"dense_vecs": [[0.1] * 1024]}
    return resp


class TestBGERetryPolicy:
    """bge_retry retries 429/503 (transient sidecar overload) but not client errors."""

    def test_bge_retry_configured_for_http_status(self):
        """bge_retry has retry_on_http_status enabled and covers 429 + 503."""
        from src.services._retry import RETRYABLE_HTTP_STATUS_CODES

        assert 429 in RETRYABLE_HTTP_STATUS_CODES
        assert 503 in RETRYABLE_HTTP_STATUS_CODES

    def test_sync_encode_dense_retries_on_503_then_succeeds(self, sync_client):
        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(
            side_effect=[_failing_resp(503), _failing_resp(503), _dense_ok_resp()]
        )

        result = sync_client.encode_dense(["hello"])

        assert len(result.vectors) == 1
        assert sync_client._client.post.call_count == 3  # 2 retries then success

    def test_sync_encode_hybrid_retries_on_429_then_succeeds(self, sync_client):
        ok = MagicMock()
        ok.raise_for_status = MagicMock()
        ok.json.return_value = {
            "dense_vecs": [[0.1] * 1024],
            "lexical_weights": [{"indices": [1], "values": [0.5]}],
        }
        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(side_effect=[_failing_resp(429), ok])

        result = sync_client.encode_hybrid(["hello"])

        assert len(result.dense_vecs) == 1
        assert sync_client._client.post.call_count == 2

    def test_sync_encode_dense_exhausts_retries_and_reraises(self, sync_client):
        """After max_attempts consecutive 503s the error is reraised (reraise=True)."""
        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(return_value=_failing_resp(503))

        with pytest.raises(httpx.HTTPStatusError):
            sync_client.encode_dense(["hello"])

        assert sync_client._client.post.call_count == 3  # max_attempts, no infinite loop

    def test_sync_encode_dense_does_not_retry_on_400(self, sync_client):
        """A non-retryable client error (400) fails fast without retry."""
        sync_client._client = MagicMock()
        sync_client._client.post = MagicMock(return_value=_failing_resp(400))

        with pytest.raises(httpx.HTTPStatusError):
            sync_client.encode_dense(["hello"])

        assert sync_client._client.post.call_count == 1  # no retry on 400

    async def test_async_encode_dense_retries_on_503_then_succeeds(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            side_effect=[_failing_resp(503), _failing_resp(503), _dense_ok_resp()]
        )
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_dense(["hello"])

        assert len(result.vectors) == 1
        assert mock_http.post.call_count == 3


# ── Issue #3375: client batch_size is real and every request is capped at 64 ──


BGE_REQUEST_CAP = 64  # sidecar ENCODE_MAX_ITEMS: >64 texts per request → 422


def _marker(text: str) -> int:
    """Global input index encoded in fixture texts shaped ``t<index>``."""
    return int(text[1:])


def _chunk_response(chunk: list[str], families: tuple[str, ...]) -> MagicMock:
    """Build a sidecar response echoing each text's global index per vector family."""
    data: dict = {"processing_time": 0.01}
    if "dense" in families:
        data["dense_vecs"] = [[float(_marker(t))] * 1024 for t in chunk]
    if "sparse" in families:
        data["lexical_weights"] = [{"indices": [_marker(t)], "values": [1.0]} for t in chunk]
    if "colbert" in families:
        data["colbert_vecs"] = [[[float(_marker(t))] * 1024] for t in chunk]
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _capture_async_http(captured_sizes: list[int], families: tuple[str, ...]) -> AsyncMock:
    """AsyncMock httpx client recording per-request text counts (issue #3375)."""
    mock_http = AsyncMock()
    mock_http.is_closed = False

    def _post(url, json=None, **_kwargs):
        chunk = json["texts"]
        captured_sizes.append(len(chunk))
        return _chunk_response(chunk, families)

    mock_http.post = AsyncMock(side_effect=_post)
    return mock_http


def _capture_sync_http(captured_sizes: list[int], families: tuple[str, ...]) -> MagicMock:
    """Sync MagicMock httpx client recording per-request text counts (issue #3375)."""
    mock_http = MagicMock()

    def _post(url, json=None, **_kwargs):
        chunk = json["texts"]
        captured_sizes.append(len(chunk))
        return _chunk_response(chunk, families)

    mock_http.post = MagicMock(side_effect=_post)
    return mock_http


class TestClientSideBatching:
    """Client splits arbitrary input into requests of min(batch_size, 64) texts.

    The sidecar rejects >64 texts per encode request (ENCODE_MAX_ITEMS → 422),
    so every sync/async encode method must send sequential bounded requests,
    preserve order/cardinality, map partial-failure indexes back to global
    input positions, and perform zero requests for empty input (#3375).
    """

    @pytest.mark.parametrize(
        ("count", "expected_sizes"),
        [
            (65, [32, 32, 1]),
            (129, [32, 32, 32, 32, 1]),
            (300, [32] * 9 + [12]),
        ],
    )
    async def test_encode_dense_splits_large_input_into_bounded_requests(
        self, client, count, expected_sizes
    ):
        texts = [f"t{i}" for i in range(count)]
        captured_sizes: list[int] = []
        mock_http = _capture_async_http(captured_sizes, ("dense",))
        client._client = mock_http

        result = await client.encode_dense(texts)

        assert captured_sizes == expected_sizes
        assert max(captured_sizes) <= BGE_REQUEST_CAP
        assert len(result.vectors) == count
        assert [int(v[0]) for v in result.vectors] == list(range(count))

    @pytest.mark.parametrize(
        ("count", "expected_sizes"),
        [
            (65, [32, 32, 1]),
            (129, [32, 32, 32, 32, 1]),
            (300, [32] * 9 + [12]),
        ],
    )
    def test_encode_dense_sync_splits_large_input_into_bounded_requests(
        self, sync_client, count, expected_sizes
    ):
        texts = [f"t{i}" for i in range(count)]
        captured_sizes: list[int] = []
        sync_client._client = _capture_sync_http(captured_sizes, ("dense",))

        result = sync_client.encode_dense(texts)

        assert captured_sizes == expected_sizes
        assert max(captured_sizes) <= BGE_REQUEST_CAP
        assert len(result.vectors) == count
        assert [int(v[0]) for v in result.vectors] == list(range(count))

    async def test_async_batch_size_above_sidecar_cap_is_capped_at_64(self, client):
        """min(configured_batch_size, 64): batch_size=100 still sends ≤64 texts per request."""
        from src.services.bge_m3_client import BGEM3Client

        big_client = BGEM3Client(base_url="http://localhost:8000", batch_size=100)
        texts = [f"t{i}" for i in range(129)]
        captured_sizes: list[int] = []
        big_client._client = _capture_async_http(captured_sizes, ("dense",))

        result = await big_client.encode_dense(texts)

        assert captured_sizes == [64, 64, 1]
        assert [int(v[0]) for v in result.vectors] == list(range(129))

    def test_sync_batch_size_above_sidecar_cap_is_capped_at_64(self, sync_client):
        """min(configured_batch_size, 64): batch_size=100 still sends ≤64 texts per request."""
        sync_client.batch_size = 100
        texts = [f"t{i}" for i in range(129)]
        captured_sizes: list[int] = []
        sync_client._client = _capture_sync_http(captured_sizes, ("dense",))

        result = sync_client.encode_dense(texts)

        assert captured_sizes == [64, 64, 1]
        assert [int(v[0]) for v in result.vectors] == list(range(129))

    @pytest.mark.parametrize("method", ["encode_sparse", "encode_hybrid", "encode_colbert"])
    async def test_async_encode_methods_split_and_preserve_order(self, client, method):
        count = 65
        texts = [f"t{i}" for i in range(count)]
        captured_sizes: list[int] = []
        families = {
            "encode_sparse": ("sparse",),
            "encode_hybrid": ("dense", "sparse", "colbert"),
            "encode_colbert": ("colbert",),
        }[method]
        client._client = _capture_async_http(captured_sizes, families)

        result = await getattr(client, method)(texts)

        assert captured_sizes == [32, 32, 1]
        primary_attr = {
            "encode_sparse": "weights",
            "encode_hybrid": "dense_vecs",
            "encode_colbert": "colbert_vecs",
        }[method]
        assert len(getattr(result, primary_attr)) == count
        if method == "encode_sparse":
            assert [w["indices"][0] for w in result.weights] == list(range(count))
        elif method == "encode_hybrid":
            assert [int(v[0]) for v in result.dense_vecs] == list(range(count))
            assert [w["indices"][0] for w in result.lexical_weights] == list(range(count))
            assert result.colbert_vecs is not None
            assert [int(tv[0][0]) for tv in result.colbert_vecs] == list(range(count))
        else:
            assert [int(tv[0][0]) for tv in result.colbert_vecs] == list(range(count))

    @pytest.mark.parametrize("method", ["encode_sparse", "encode_hybrid", "encode_colbert"])
    def test_sync_encode_methods_split_and_preserve_order(self, sync_client, method):
        count = 65
        texts = [f"t{i}" for i in range(count)]
        captured_sizes: list[int] = []
        families = {
            "encode_sparse": ("sparse",),
            "encode_hybrid": ("dense", "sparse", "colbert"),
            "encode_colbert": ("colbert",),
        }[method]
        sync_client._client = _capture_sync_http(captured_sizes, families)

        result = getattr(sync_client, method)(texts)

        assert captured_sizes == [32, 32, 1]
        primary_attr = {
            "encode_sparse": "weights",
            "encode_hybrid": "dense_vecs",
            "encode_colbert": "colbert_vecs",
        }[method]
        assert len(getattr(result, primary_attr)) == count
        if method == "encode_sparse":
            assert [w["indices"][0] for w in result.weights] == list(range(count))
        elif method == "encode_hybrid":
            assert [int(v[0]) for v in result.dense_vecs] == list(range(count))
            assert [w["indices"][0] for w in result.lexical_weights] == list(range(count))
            assert result.colbert_vecs is not None
            assert [int(tv[0][0]) for tv in result.colbert_vecs] == list(range(count))
        else:
            assert [int(tv[0][0]) for tv in result.colbert_vecs] == list(range(count))

    async def test_async_empty_input_performs_zero_requests(self, client):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock()
        mock_http.is_closed = False
        client._client = mock_http

        assert (await client.encode_dense([])).vectors == []
        assert (await client.encode_sparse([])).weights == []
        assert (await client.encode_hybrid([])).dense_vecs == []
        assert (await client.encode_colbert([])).colbert_vecs == []
        mock_http.post.assert_not_awaited()

    def test_sync_empty_input_performs_zero_requests(self, sync_client):
        mock_http = MagicMock()
        mock_http.post = MagicMock()
        sync_client._client = mock_http

        assert sync_client.encode_dense([]).vectors == []
        assert sync_client.encode_sparse([]).weights == []
        assert sync_client.encode_hybrid([]).dense_vecs == []
        assert sync_client.encode_colbert([]).colbert_vecs == []
        mock_http.post.assert_not_called()

    async def test_async_partial_failure_indexes_map_to_global_positions(self, client):
        """Per-chunk partial-failure indexes are offset by the chunk's global start."""
        client.batch_size = 2
        texts = ["t0", "t1", "t2", "t3", "t4"]

        responses = []
        for chunk, failures in (
            (["t0", "t1"], [{"index": 1, "error": "boom-1"}]),
            (["t2", "t3"], [{"index": 0, "error": "boom-2"}]),
            (["t4"], [{"index": 0, "error": "boom-4"}]),
        ):
            resp = _chunk_response(chunk, ("dense",))
            resp.json.return_value["partial_failures"] = failures
            responses.append(resp)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=responses)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_dense(texts)

        assert [(f["index"], f["error"]) for f in result.partial_failures] == [
            (1, "boom-1"),
            (2, "boom-2"),
            (4, "boom-4"),
        ]
        assert len(result.vectors) == 5

    def test_sync_hybrid_partial_failure_indexes_map_to_global_positions(self, sync_client):
        """Per-chunk partial-failure indexes are offset by the chunk's global start."""
        sync_client.batch_size = 2
        texts = ["t0", "t1", "t2", "t3", "t4"]

        responses = []
        for chunk, failures in (
            (["t0", "t1"], [{"index": 0, "error": "boom-0"}]),
            (["t2", "t3"], []),
            (["t4"], [{"index": 0, "error": "boom-4"}]),
        ):
            resp = _chunk_response(chunk, ("dense", "sparse"))
            resp.json.return_value["partial_failures"] = failures
            responses.append(resp)

        mock_http = MagicMock()
        mock_http.post = MagicMock(side_effect=responses)
        sync_client._client = mock_http

        result = sync_client.encode_hybrid(texts)

        assert [(f["index"], f["error"]) for f in result.partial_failures] == [
            (0, "boom-0"),
            (4, "boom-4"),
        ]
        assert len(result.dense_vecs) == 5
        assert len(result.lexical_weights) == 5
