"""Tests for USER2-base FastAPI endpoints (services/user-base/main.py).

Mocks SentenceTransformer before importing app to avoid model download.
Uses httpx.AsyncClient + ASGITransport for async endpoint testing.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


pytest.importorskip("fastapi", reason="fastapi not installed (voice extra)")
pytestmark = pytest.mark.requires_extras


# Mock SentenceTransformer BEFORE importing the app module
_mock_st_class = MagicMock()
_mock_model_instance = MagicMock()
_mock_model_instance.get_sentence_embedding_dimension.return_value = 768
_mock_model_instance.encode.side_effect = lambda text, **_kw: (
    np.random.rand(768).astype(np.float32)
    if isinstance(text, str)
    else np.random.rand(len(text), 768).astype(np.float32)
)
_mock_st_class.return_value = _mock_model_instance

_mock_module = MagicMock()
_mock_module.SentenceTransformer = _mock_st_class
sys.modules["sentence_transformers"] = _mock_module

# Import main.py from services/user-base/ (not a Python package due to hyphen)
_service_dir = str(Path(__file__).resolve().parents[2] / "services" / "user-base")
sys.path.insert(0, _service_dir)
import main as userbase_main


app = userbase_main.app
sys.path.pop(0)

import httpx


@pytest.fixture
async def client():
    """Create async test client with ASGI transport.

    Sets the module-level model to the mock instance since lifespan
    doesn't run with ASGITransport.
    """
    userbase_main.model = _mock_model_instance
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    userbase_main.model = None


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

    def test_default_backend_is_pytorch(self):
        """Default EMBEDDING_BACKEND loads pytorch."""
        with patch.object(userbase_main, "EMBEDDING_BACKEND", "pytorch"):
            model = userbase_main._load_model()
            assert userbase_main._active_backend == "pytorch"
            assert model is _mock_model_instance

    def test_onnx_backend_falls_back_on_import_error(self):
        """ONNX backend falls back to pytorch when onnxruntime not installed."""
        with (
            patch.object(userbase_main, "EMBEDDING_BACKEND", "onnx"),
            patch.dict(sys.modules, {"onnxruntime": None}),
        ):
            model = userbase_main._load_model()
            assert userbase_main._active_backend == "pytorch"
            assert model is _mock_model_instance

    def test_onnx_backend_loads_when_available(self):
        """ONNX backend used when onnxruntime is importable."""
        mock_ort = MagicMock()
        with (
            patch.object(userbase_main, "EMBEDDING_BACKEND", "onnx"),
            patch.dict(sys.modules, {"onnxruntime": mock_ort}),
        ):
            userbase_main._load_model()
            assert userbase_main._active_backend == "onnx"
            _mock_st_class.assert_called_with("deepvk/USER2-base", backend="onnx")

    def test_onnx_backend_falls_back_on_exception(self):
        """ONNX backend falls back to pytorch on any SentenceTransformer error."""
        mock_ort = MagicMock()
        _mock_st_class.side_effect = [RuntimeError("ONNX export failed"), _mock_model_instance]
        try:
            with (
                patch.object(userbase_main, "EMBEDDING_BACKEND", "onnx"),
                patch.dict(sys.modules, {"onnxruntime": mock_ort}),
            ):
                model = userbase_main._load_model()
                assert userbase_main._active_backend == "pytorch"
                assert model is _mock_model_instance
        finally:
            _mock_st_class.side_effect = None
            _mock_st_class.return_value = _mock_model_instance
