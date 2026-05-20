"""Tests for bge-m3-api FastAPI endpoints.

Covers /encode/sparse, /encode/colbert, /encode/hybrid, /encode/dense,
/health, /metrics, and config defaults.

All sys.modules mocking is fixture-scoped (no module-level pollution).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import numpy as np
import pytest


pytest.importorskip("fastapi", reason="fastapi not installed (voice extra)")
pytestmark = pytest.mark.requires_extras
***REMOVED*** ── Fake model that returns deterministic numpy arrays ──
_DENSE_DIM = 1024
_COLBERT_DIM = 1024

_BGE_SERVICE_DIR = str(Path(__file__).parents[2] / "services" / "bge-m3-api")


def _make_fake_model():
    """Return a mock BGEM3FlagModel with a working .encode()."""
    model = MagicMock()

    def fake_encode(
        texts,
        *,
        batch_size=12,
        max_length=2048,
        return_dense=False,
        return_sparse=False,
        return_colbert_vecs=False,
    ):
        n = len(texts)
        result = {}
        if return_dense:
            result["dense_vecs"] = np.random.rand(n, _DENSE_DIM).astype(np.float32)
        if return_sparse:
            result["lexical_weights"] = [
                {str(i): 0.5 + i * 0.1 for i in range(3)} for _ in range(n)
            ]
        if return_colbert_vecs:
            result["colbert_vecs"] = [
                np.random.rand(5, _COLBERT_DIM).astype(np.float32) for _ in range(n)
            ]
        return result

    model.encode = MagicMock(side_effect=fake_encode)
    return model


@pytest.fixture(scope="module")
def bge_app():
    """Mock heavy deps, import bge-m3-api app, install fake model.

    Uses MonkeyPatch.context() for automatic teardown of sys.modules entries.
    """
    with pytest.MonkeyPatch.context() as mp:
        mock_flag = MagicMock()
        mock_prom = MagicMock()
        mock_prom.make_asgi_app = MagicMock(return_value=MagicMock())
        mock_lf = MagicMock()
        mock_lf.observe = lambda *_a, **_k: lambda f: f

        mp.setitem(sys.modules, "FlagEmbedding", mock_flag)
        mp.setitem(sys.modules, "prometheus_client", mock_prom)
        mp.setitem(sys.modules, "langfuse", mock_lf)
        mp.syspath_prepend(_BGE_SERVICE_DIR)

        import app as app_module
        from app import app as fastapi_app

        import config as _cfg

        fake_model = _make_fake_model()
        app_module._model = fake_model
        app_module.get_model = MagicMock(return_value=fake_model)

        yield {
            "app": fastapi_app,
            "app_module": app_module,
            "config": _cfg,
            "fake_model": fake_model,
        }

        ***REMOVED*** Clean up cached service imports (not mocks — real modules imported
        ***REMOVED*** via syspath_prepend that shouldn't leak to other test files).
        for mod_name in ("app", "config"):
            sys.modules.pop(mod_name, None)


@pytest.fixture
async def client(bge_app):
    transport = httpx.ASGITransport(app=bge_app["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


***REMOVED*** ── Endpoint tests ──


class TestHealthEndpoint:
    async def test_health_returns_status(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data


class TestEncodeSparse:
    async def test_sparse_single_text(self, client):
        resp = await client.post("/encode/sparse", json={"texts": ["hello"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "lexical_weights" in data
        assert isinstance(data["lexical_weights"], list)
        assert len(data["lexical_weights"]) == 1
        ***REMOVED*** Each item has indices + values
        item = data["lexical_weights"][0]
        assert "indices" in item
        assert "values" in item


class TestEncodeColbert:
    async def test_colbert_single_text(self, client):
        resp = await client.post("/encode/colbert", json={"texts": ["hello"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "colbert_vecs" in data
        assert isinstance(data["colbert_vecs"], list)
        assert len(data["colbert_vecs"]) == 1
        ***REMOVED*** Each embedding is list of lists (multi-vector)
        vec = data["colbert_vecs"][0]
        assert isinstance(vec, list)
        assert isinstance(vec[0], list)


class TestEncodeHybrid:
    async def test_hybrid_single_text(self, client):
        resp = await client.post("/encode/hybrid", json={"texts": ["hello"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "dense_vecs" in data
        assert "lexical_weights" in data
        assert "colbert_vecs" in data


class TestEncodeDense:
    async def test_dense_empty_texts(self, client):
        resp = await client.post("/encode/dense", json={"texts": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["dense_vecs"] == []


class TestMetrics:
    async def test_metrics_endpoint(self, client):
        resp = await client.get("/metrics")
        ***REMOVED*** Prometheus metrics sub-app is mocked, so may return 200 or error
        ***REMOVED*** The important thing is the route exists and doesn't 404
        assert resp.status_code != 404


class TestConfigDefaults:
    def test_settings_defaults(self, bge_app):
        _cfg = bge_app["config"]
        assert _cfg.settings.MAX_LENGTH == 2048
        assert _cfg.settings.BATCH_SIZE == 12
        assert _cfg.settings.USE_FP16 is True
        assert _cfg.settings.RERANK_MAX_DOCS == 30
        assert _cfg.settings.RERANK_MAX_LENGTH == 512


class TestPartialFailureIsolation:
    """Tests for per-item validation and partial failure isolation in batch encode."""

    async def test_dense_batch_with_empty_string_returns_partial_failure(self, client):
        """POST /encode/dense with ['hello', '', 'world'] returns 200 with partial_failures."""
        resp = await client.post("/encode/dense", json={"texts": ["hello", "", "world"]})
        assert resp.status_code == 200
        data = resp.json()
        ***REMOVED*** Response cardinality matches input cardinality
        assert len(data["dense_vecs"]) == 3
        ***REMOVED*** partial_failures reports index 1
        assert "partial_failures" in data
        assert len(data["partial_failures"]) == 1
        assert data["partial_failures"][0]["index"] == 1
        assert "error" in data["partial_failures"][0]
        ***REMOVED*** Valid items have non-zero vectors
        assert any(v != 0.0 for v in data["dense_vecs"][0])
        assert any(v != 0.0 for v in data["dense_vecs"][2])
        ***REMOVED*** Invalid item has zero-vector sentinel
        assert all(v == 0.0 for v in data["dense_vecs"][1])
        assert len(data["dense_vecs"][1]) == 1024

    async def test_sparse_batch_with_empty_string(self, client):
        """POST /encode/sparse with ['hello', '', 'world'] returns sentinel for empty."""
        resp = await client.post("/encode/sparse", json={"texts": ["hello", "", "world"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lexical_weights"]) == 3
        assert "partial_failures" in data
        assert len(data["partial_failures"]) == 1
        assert data["partial_failures"][0]["index"] == 1
        ***REMOVED*** Invalid item has empty indices/values
        assert data["lexical_weights"][1]["indices"] == []
        assert data["lexical_weights"][1]["values"] == []
        ***REMOVED*** Valid items have non-empty weights
        assert len(data["lexical_weights"][0]["indices"]) > 0
        assert len(data["lexical_weights"][2]["indices"]) > 0

    async def test_colbert_batch_with_empty_string(self, client):
        """POST /encode/colbert with ['hello', '', 'world'] returns sentinel for empty."""
        resp = await client.post("/encode/colbert", json={"texts": ["hello", "", "world"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["colbert_vecs"]) == 3
        assert "partial_failures" in data
        assert len(data["partial_failures"]) == 1
        assert data["partial_failures"][0]["index"] == 1
        ***REMOVED*** Invalid item: single zero-vector token [[0.0]*1024]
        assert len(data["colbert_vecs"][1]) == 1
        assert all(v == 0.0 for v in data["colbert_vecs"][1][0])
        assert len(data["colbert_vecs"][1][0]) == 1024
        ***REMOVED*** Valid items have multi-token vectors
        assert len(data["colbert_vecs"][0]) > 0
        assert len(data["colbert_vecs"][2]) > 0

    async def test_hybrid_batch_with_empty_string(self, client):
        """POST /encode/hybrid with ['hello', '', 'world'] returns sentinels for all types."""
        resp = await client.post("/encode/hybrid", json={"texts": ["hello", "", "world"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "partial_failures" in data
        assert len(data["partial_failures"]) == 1
        assert data["partial_failures"][0]["index"] == 1
        ***REMOVED*** Dense sentinel
        assert len(data["dense_vecs"]) == 3
        assert all(v == 0.0 for v in data["dense_vecs"][1])
        ***REMOVED*** Sparse sentinel
        assert len(data["lexical_weights"]) == 3
        assert data["lexical_weights"][1]["indices"] == []
        assert data["lexical_weights"][1]["values"] == []
        ***REMOVED*** ColBERT sentinel
        assert len(data["colbert_vecs"]) == 3
        assert len(data["colbert_vecs"][1]) == 1
        assert all(v == 0.0 for v in data["colbert_vecs"][1][0])

    async def test_all_valid_items_no_partial_failures(self, client):
        """A fully-valid batch returns empty partial_failures (backward compatible)."""
        resp = await client.post("/encode/dense", json={"texts": ["hello", "world"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["partial_failures"] == []
        assert len(data["dense_vecs"]) == 2

    async def test_dense_all_items_invalid_returns_all_sentinels(self, client):
        """When ALL items fail validation, response is all sentinels with no model call."""
        resp = await client.post("/encode/dense", json={"texts": ["", "   "]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["dense_vecs"]) == 2
        assert len(data["partial_failures"]) == 2
        ***REMOVED*** Both are zero sentinels
        assert all(v == 0.0 for v in data["dense_vecs"][0])
        assert all(v == 0.0 for v in data["dense_vecs"][1])

    async def test_model_exception_still_returns_500(self, client, bge_app):
        """Infrastructure/model errors still produce HTTP 500."""
        fake_model = bge_app["fake_model"]
        original_side_effect = fake_model.encode.side_effect
        fake_model.encode.side_effect = RuntimeError("GPU OOM")
        try:
            resp = await client.post("/encode/dense", json={"texts": ["hello", "world"]})
            assert resp.status_code == 500
        finally:
            fake_model.encode.side_effect = original_side_effect


class TestWarmup:
    async def test_warmup_skips_colbert(self, bge_app):
        """Lifespan warmup avoids ColBERT to keep startup memory bounded."""
        app_module = bge_app["app_module"]
        fake_model = bge_app["fake_model"]

        fake_model.encode.reset_mock()

        ***REMOVED*** Run the lifespan startup directly (no ASGI runner needed)
        gen = app_module.lifespan(None)
        await gen.__aenter__()
        await gen.__aexit__(None, None, None)

        assert fake_model.encode.called, "Warmup must call model.encode()"
        warmup_kwargs = fake_model.encode.call_args.kwargs
        assert warmup_kwargs.get("return_colbert_vecs") is False, (
            f"Warmup must use return_colbert_vecs=False to reduce startup memory, "
            f"got return_colbert_vecs={warmup_kwargs.get('return_colbert_vecs')}"
        )
