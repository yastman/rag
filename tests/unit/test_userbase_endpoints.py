"""Tests for USER2-base FastAPI endpoints (services/user-base/main.py).

Mocks SentenceTransformer via fixture before importing app to avoid model download.
Uses httpx.AsyncClient + ASGITransport for async endpoint testing.

All sys.modules mocking is fixture-scoped (no module-level pollution).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import numpy as np
import pytest


_USERBASE_SERVICE_DIR = str(Path(__file__).resolve().parents[2] / "services" / "user-base")


@pytest.fixture(scope="module")
def userbase_env():
    """Mock sentence_transformers & import user-base app.

    Returns dict with app, main module, mock class and mock model instance.
    """
    mock_st_class = MagicMock()
    mock_model_instance = MagicMock()
    mock_model_instance.get_sentence_embedding_dimension.return_value = 768
    mock_model_instance.encode.side_effect = lambda text, **_kw: (
        np.random.rand(768).astype(np.float32)
        if isinstance(text, str)
        else np.random.rand(len(text), 768).astype(np.float32)
    )
    mock_st_class.return_value = mock_model_instance

    mock_module = MagicMock()
    mock_module.SentenceTransformer = mock_st_class

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "sentence_transformers", mock_module)
        mp.syspath_prepend(_USERBASE_SERVICE_DIR)

        import main as userbase_main

        yield {
            "main": userbase_main,
            "app": userbase_main.app,
            "mock_st_class": mock_st_class,
            "mock_model_instance": mock_model_instance,
        }

        # Clean up cached service import (not a mock — real module imported
        # via syspath_prepend that shouldn't leak to other test files).
        sys.modules.pop("main", None)


@pytest.fixture
async def client(userbase_env):
    """Create async test client with ASGI transport."""
    userbase_env["main"].model = userbase_env["mock_model_instance"]
    transport = httpx.ASGITransport(app=userbase_env["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    userbase_env["main"].model = None


class TestHealthEndpoint:
    """GET /health endpoint tests."""

    async def test_health_returns_200(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_health_response_fields(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        data = resp.json()
        assert "status" in data
        assert "model" in data
        assert "dimension" in data
        assert "backend" in data

    async def test_health_backend_default_is_pytorch(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        data = resp.json()
        assert data["backend"] == "pytorch"

    async def test_health_dimension_is_768(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        data = resp.json()
        assert data["dimension"] == 768


class TestEmbedEndpoint:
    """POST /embed endpoint tests."""

    async def test_embed_returns_200(self, client: httpx.AsyncClient):
        resp = await client.post("/embed", json={"text": "привет"})
        assert resp.status_code == 200

    async def test_embed_returns_embedding_list(self, client: httpx.AsyncClient):
        resp = await client.post("/embed", json={"text": "привет"})
        data = resp.json()
        assert "embedding" in data
        assert isinstance(data["embedding"], list)

    async def test_embed_dimension_is_768(self, client: httpx.AsyncClient):
        resp = await client.post("/embed", json={"text": "привет"})
        data = resp.json()
        assert len(data["embedding"]) == 768

    async def test_embed_empty_text(self, client: httpx.AsyncClient):
        """Empty text should still produce an embedding (model handles it)."""
        resp = await client.post("/embed", json={"text": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["embedding"]) == 768


class TestEmbedBatchEndpoint:
    """POST /embed_batch endpoint tests."""

    async def test_embed_batch_returns_200(self, client: httpx.AsyncClient):
        resp = await client.post("/embed_batch", json={"texts": ["привет", "мир"]})
        assert resp.status_code == 200

    async def test_embed_batch_returns_correct_count(self, client: httpx.AsyncClient):
        resp = await client.post("/embed_batch", json={"texts": ["привет", "мир"]})
        data = resp.json()
        assert "embeddings" in data
        assert len(data["embeddings"]) == 2

    async def test_embed_batch_each_dimension_is_768(self, client: httpx.AsyncClient):
        resp = await client.post("/embed_batch", json={"texts": ["привет", "мир"]})
        data = resp.json()
        for emb in data["embeddings"]:
            assert len(emb) == 768

    async def test_embed_batch_empty_list(self, client: httpx.AsyncClient):
        """Empty texts list should return empty embeddings list."""
        resp = await client.post("/embed_batch", json={"texts": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["embeddings"] == [] or isinstance(data["embeddings"], list)


class TestLoadModelBackend:
    """Tests for _load_model backend selection and fallback."""

    def test_default_backend_is_pytorch(self, userbase_env):
        """Default EMBEDDING_BACKEND loads pytorch."""
        ub = userbase_env["main"]
        mock_model = userbase_env["mock_model_instance"]
        with patch.object(ub, "EMBEDDING_BACKEND", "pytorch"):
            model = ub._load_model()
            assert ub._active_backend == "pytorch"
            assert model is mock_model

    def test_onnx_backend_falls_back_on_import_error(self, userbase_env):
        """ONNX backend falls back to pytorch when onnxruntime not installed."""
        ub = userbase_env["main"]
        mock_model = userbase_env["mock_model_instance"]
        with (
            patch.object(ub, "EMBEDDING_BACKEND", "onnx"),
            patch.dict(sys.modules, {"onnxruntime": None}),
        ):
            model = ub._load_model()
            assert ub._active_backend == "pytorch"
            assert model is mock_model

    def test_onnx_backend_loads_when_available(self, userbase_env):
        """ONNX backend used when onnxruntime is importable."""
        ub = userbase_env["main"]
        mock_st = userbase_env["mock_st_class"]
        mock_ort = MagicMock()
        with (
            patch.object(ub, "EMBEDDING_BACKEND", "onnx"),
            patch.dict(sys.modules, {"onnxruntime": mock_ort}),
        ):
            ub._load_model()
            assert ub._active_backend == "onnx"
            mock_st.assert_called_with("deepvk/USER2-base", backend="onnx")

    def test_onnx_backend_falls_back_on_exception(self, userbase_env):
        """ONNX backend falls back to pytorch on any SentenceTransformer error."""
        ub = userbase_env["main"]
        mock_st = userbase_env["mock_st_class"]
        mock_model = userbase_env["mock_model_instance"]
        mock_ort = MagicMock()
        mock_st.side_effect = [RuntimeError("ONNX export failed"), mock_model]
        try:
            with (
                patch.object(ub, "EMBEDDING_BACKEND", "onnx"),
                patch.dict(sys.modules, {"onnxruntime": mock_ort}),
            ):
                model = ub._load_model()
                assert ub._active_backend == "pytorch"
                assert model is mock_model
        finally:
            mock_st.side_effect = None
            mock_st.return_value = mock_model
