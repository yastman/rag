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


# ── Fake model that returns deterministic numpy arrays ──
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

        mp.setitem(sys.modules, "FlagEmbedding", mock_flag)
        mp.setitem(sys.modules, "prometheus_client", mock_prom)
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

        # Clean up cached service imports (not mocks — real modules imported
        # via syspath_prepend that shouldn't leak to other test files).
        for mod_name in ("app", "config"):
            sys.modules.pop(mod_name, None)


@pytest.fixture
def client(bge_app):
    transport = httpx.ASGITransport(app=bge_app["app"])
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ── Endpoint tests ──


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
        # Each item has indices + values
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
        # Each embedding is list of lists (multi-vector)
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
        # Prometheus metrics sub-app is mocked, so may return 200 or error
        # The important thing is the route exists and doesn't 404
        assert resp.status_code != 404


class TestConfigDefaults:
    def test_settings_defaults(self, bge_app):
        _cfg = bge_app["config"]
        assert _cfg.settings.MAX_LENGTH == 2048
        assert _cfg.settings.BATCH_SIZE == 12
        assert _cfg.settings.USE_FP16 is True
        assert _cfg.settings.RERANK_MAX_DOCS == 30
        assert _cfg.settings.RERANK_MAX_LENGTH == 512
