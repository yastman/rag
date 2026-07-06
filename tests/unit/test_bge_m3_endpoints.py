"""Tests for bge-m3-api FastAPI endpoints.

Covers /encode/sparse, /encode/colbert, /encode/hybrid, /encode/dense,
/health, /metrics, and config defaults.

All sys.modules mocking is fixture-scoped (no module-level pollution).

Gate test (no fastapi required):
    test_encode_colbert_multivector_shape_gate — uses BGEM3Client with mocked
    httpx; verifies colbert encode returns list-of-vectors each with 1024-dim.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import numpy as np
import pytest


# ── Gate test — no FastAPI required, runs in core tier ────────────────────────


@pytest.mark.no_services
def test_encode_colbert_multivector_shape_gate() -> None:
    """CLOSE-GATE: colbert encode returns list-of-vectors, each with shape (1024,).

    Uses BGEM3Client with mocked httpx — no live service, no fastapi.
    The multi-vector shape is: colbert_vecs[text_i][token_j] has len 1024.
    """
    from src.services.bge_m3_client import BGEM3Client

    # Three tokens per text, each 1024-dim — realistic ColBERT output.
    token_vec = [0.1] * 1024
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "colbert_vecs": [[token_vec, token_vec, token_vec]],  # 1 text, 3 tokens
        "processing_time": 0.05,
    }

    import asyncio

    async def _run() -> None:
        client = BGEM3Client(base_url="http://localhost:8000")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._client = mock_http

        result = await client.encode_colbert(["hello world"])

        # Shape assertions — the gate this card closes
        assert isinstance(result.colbert_vecs, list), "colbert_vecs must be a list"
        assert len(result.colbert_vecs) == 1, "one text → one entry"
        token_vecs = result.colbert_vecs[0]
        assert isinstance(token_vecs, list), "each text entry must be a list of token vecs"
        assert len(token_vecs) == 3, "expected 3 token vectors"
        for i, vec in enumerate(token_vecs):
            assert len(vec) == 1024, f"token_vecs[{i}] must have dim 1024, got {len(vec)}"

    asyncio.run(_run())


# ── FastAPI-dependent tests — skipped when fastapi not installed ───────────────
# importorskip is replaced by an explicit pytest.skip() inside fixtures so the
# gate test above still collects when fastapi is absent, but the skip message
# is actionable: "run via: make test-bge-extras".

# ── Fake model that returns deterministic numpy arrays ──
_DENSE_DIM = 1024
_COLBERT_DIM = 1024

_BGE_SERVICE_DIR = str(Path(__file__).parents[2] / "services" / "bge-m3-api")


class FakeONNXModel:
    """Fake ONNXEmbeddingModel with a working .encode()."""

    def __init__(self, session, tokenizer):
        self.session = session
        self.tokenizer = tokenizer

    def encode(
        self,
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
            # Return Qdrant sparse format directly (indices + values)
            result["lexical_weights"] = [
                {"indices": list(range(3)), "values": [0.5 + i * 0.1 for i in range(3)]}
                for _ in range(n)
            ]
        if return_colbert_vecs:
            result["colbert_vecs"] = [
                np.random.rand(5, _COLBERT_DIM).astype(np.float32) for _ in range(n)
            ]
        return result


@pytest.fixture(scope="module")
def bge_app():
    """Mock heavy deps, import bge-m3-api app, install fake model.

    Uses MonkeyPatch.context() for automatic teardown of sys.modules entries.
    Requires fastapi (bge-extras lane: uv sync --extra bge-extras).
    """
    import importlib

    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("fastapi not installed — run via: make test-bge-extras")
    with pytest.MonkeyPatch.context() as mp:
        mock_ort = MagicMock()
        mock_ort.InferenceSession = MagicMock()
        mock_ort.GraphOptimizationLevel = MagicMock()
        mock_ort.GraphOptimizationLevel.ORT_ENABLE_ALL = 1
        mock_ort.SessionOptions = MagicMock

        mock_transformers = MagicMock()
        mock_transformers.AutoTokenizer.from_pretrained = MagicMock(return_value=MagicMock())

        mock_prom = MagicMock()
        mock_prom.make_asgi_app = MagicMock(return_value=MagicMock())

        mp.setitem(sys.modules, "onnxruntime", mock_ort)
        mp.setitem(sys.modules, "transformers", mock_transformers)
        mp.setitem(sys.modules, "prometheus_client", mock_prom)
        mp.syspath_prepend(_BGE_SERVICE_DIR)

        import app as app_module
        from app import app as fastapi_app

        import config as _cfg

        fake_model = FakeONNXModel(session=MagicMock(), tokenizer=MagicMock())
        app_module._onnx_session = MagicMock()
        app_module._tokenizer = MagicMock()
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
async def client(bge_app):
    transport = httpx.ASGITransport(app=bge_app["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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

    # test_traceparent_header_is_extracted removed: OTel propagate removed from app.py
    # (OpenTelemetry fully removed, card_81add5ba4a66). No traceparent handling to test.


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
        assert _cfg.settings.MODEL_REVISION == "5617a9f61b028005a4858fdac845db406aefb181"
        assert _cfg.settings.RERANK_MAX_DOCS == 30
        assert _cfg.settings.RERANK_MAX_LENGTH == 512


class TestPartialFailureIsolation:
    """Tests for per-item validation and partial failure isolation in batch encode."""

    async def test_dense_batch_with_empty_string_returns_partial_failure(self, client):
        """POST /encode/dense with ['hello', '', 'world'] returns 200 with partial_failures."""
        resp = await client.post("/encode/dense", json={"texts": ["hello", "", "world"]})
        assert resp.status_code == 200
        data = resp.json()
        # Response cardinality matches input cardinality
        assert len(data["dense_vecs"]) == 3
        # partial_failures reports index 1
        assert "partial_failures" in data
        assert len(data["partial_failures"]) == 1
        assert data["partial_failures"][0]["index"] == 1
        assert "error" in data["partial_failures"][0]
        # Valid items have non-zero vectors
        assert any(v != 0.0 for v in data["dense_vecs"][0])
        assert any(v != 0.0 for v in data["dense_vecs"][2])
        # Invalid item has zero-vector sentinel
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
        # Invalid item has empty indices/values
        assert data["lexical_weights"][1]["indices"] == []
        assert data["lexical_weights"][1]["values"] == []
        # Valid items have non-empty weights
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
        # Invalid item: single zero-vector token [[0.0]*1024]
        assert len(data["colbert_vecs"][1]) == 1
        assert all(v == 0.0 for v in data["colbert_vecs"][1][0])
        assert len(data["colbert_vecs"][1][0]) == 1024
        # Valid items have multi-token vectors
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
        # Dense sentinel
        assert len(data["dense_vecs"]) == 3
        assert all(v == 0.0 for v in data["dense_vecs"][1])
        # Sparse sentinel
        assert len(data["lexical_weights"]) == 3
        assert data["lexical_weights"][1]["indices"] == []
        assert data["lexical_weights"][1]["values"] == []
        # ColBERT sentinel
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
        # Both are zero sentinels
        assert all(v == 0.0 for v in data["dense_vecs"][0])
        assert all(v == 0.0 for v in data["dense_vecs"][1])

    async def test_model_exception_still_returns_500(self, client, bge_app):
        """Infrastructure/model errors still produce HTTP 500."""
        fake_model = bge_app["fake_model"]
        original_encode = fake_model.encode
        fake_model.encode = MagicMock(side_effect=RuntimeError("ONNX session error"))
        try:
            resp = await client.post("/encode/dense", json={"texts": ["hello", "world"]})
            assert resp.status_code == 500
        finally:
            fake_model.encode = original_encode  # restore original method


# ── ONNX output contract tests ─────────────────────────────────────────────────


def _make_mock_session(output_names: list[str]) -> MagicMock:
    """Return a mock InferenceSession whose get_outputs() returns the given names."""
    mock_session = MagicMock()
    mock_outputs = []
    for name in output_names:
        out = MagicMock()
        out.name = name
        mock_outputs.append(out)
    mock_session.get_outputs.return_value = mock_outputs
    mock_session.get_inputs.return_value = []
    return mock_session


def _import_onnx_model_class():
    """Import ONNXEmbeddingModel with heavy deps mocked (no real ONNX/transformers)."""
    heavy_mocks = {
        "onnxruntime": MagicMock(),
        "fastapi": MagicMock(),
        "transformers": MagicMock(),
        "prometheus_client": MagicMock(),
        "opentelemetry": MagicMock(),
        "opentelemetry.context": MagicMock(),
        "opentelemetry.propagate": MagicMock(),
    }
    for attr in ("Counter", "Gauge", "Histogram"):
        setattr(heavy_mocks["prometheus_client"], attr, MagicMock(return_value=MagicMock()))
    heavy_mocks["prometheus_client"].make_asgi_app = MagicMock(return_value=MagicMock())

    with pytest.MonkeyPatch.context() as mp:
        for mod, mock in heavy_mocks.items():
            mp.setitem(sys.modules, mod, mock)
        mp.syspath_prepend(_BGE_SERVICE_DIR)
        sys.modules.pop("app", None)
        import app as _app_module

        cls = _app_module.ONNXEmbeddingModel
        sys.modules.pop("app", None)
    return cls


@pytest.mark.no_services
def test_onnx_output_order_correct_names_initialises_ok() -> None:
    """ONNXEmbeddingModel.__init__ succeeds when output names match expected order."""
    ONNXEmbeddingModel = _import_onnx_model_class()
    session = _make_mock_session(["dense_vecs", "sparse_vecs", "colbert_vecs"])
    model = ONNXEmbeddingModel(session=session, tokenizer=MagicMock())
    assert model._output_names == ["dense_vecs", "sparse_vecs", "colbert_vecs"]


@pytest.mark.no_services
def test_onnx_output_order_mismatch_raises_assertion() -> None:
    """ONNXEmbeddingModel.__init__ raises AssertionError when output order is wrong."""
    ONNXEmbeddingModel = _import_onnx_model_class()
    session = _make_mock_session(["colbert_vecs", "dense_vecs", "sparse_vecs"])
    with pytest.raises(AssertionError, match="ONNX model output order changed"):
        ONNXEmbeddingModel(session=session, tokenizer=MagicMock())


@pytest.mark.no_services
def test_onnx_output_name_mismatch_wrong_names_raises_assertion() -> None:
    """ONNXEmbeddingModel.__init__ raises AssertionError when output names differ."""
    ONNXEmbeddingModel = _import_onnx_model_class()
    session = _make_mock_session(["output_0", "output_1", "output_2"])
    with pytest.raises(AssertionError, match="ONNX model output order changed"):
        ONNXEmbeddingModel(session=session, tokenizer=MagicMock())


@pytest.mark.no_services
def test_get_model_file_not_found_raises(tmp_path) -> None:
    """get_model() raises FileNotFoundError when the ONNX model file doesn't exist."""
    heavy_mocks = {
        "onnxruntime": MagicMock(),
        "fastapi": MagicMock(),
        "transformers": MagicMock(),
        "prometheus_client": MagicMock(),
        "opentelemetry": MagicMock(),
        "opentelemetry.context": MagicMock(),
        "opentelemetry.propagate": MagicMock(),
    }
    for attr in ("Counter", "Gauge", "Histogram"):
        setattr(heavy_mocks["prometheus_client"], attr, MagicMock(return_value=MagicMock()))
    heavy_mocks["prometheus_client"].make_asgi_app = MagicMock(return_value=MagicMock())

    with pytest.MonkeyPatch.context() as mp:
        for mod, mock in heavy_mocks.items():
            mp.setitem(sys.modules, mod, mock)
        mp.syspath_prepend(_BGE_SERVICE_DIR)
        sys.modules.pop("app", None)
        import app as _app_module

        # Reset global session so get_model() re-runs the load path
        _app_module._onnx_session = None
        # Point ONNX_MODEL_DIR to a temp dir with no model file
        _app_module.settings = MagicMock()
        _app_module.settings.ONNX_MODEL_DIR = str(tmp_path)
        _app_module.settings.NUM_THREADS = 1

        with pytest.raises(FileNotFoundError):
            _app_module.get_model()

        sys.modules.pop("app", None)


class TestWarmup:
    async def test_warmup_skips_colbert(self, bge_app):
        """Lifespan warmup avoids ColBERT to keep startup memory bounded."""
        app_module = bge_app["app_module"]
        fake_model = bge_app["fake_model"]

        from unittest.mock import MagicMock as MM

        wrapped_encode = MM(side_effect=fake_model.encode)
        orig_encode = fake_model.encode
        fake_model.encode = wrapped_encode

        # Run the lifespan startup directly (no ASGI runner needed)
        gen = app_module.lifespan(None)
        await gen.__aenter__()
        await gen.__aexit__(None, None, None)

        assert wrapped_encode.called, "Warmup must call model.encode()"
        warmup_kwargs = wrapped_encode.call_args.kwargs
        assert warmup_kwargs.get("return_colbert_vecs") is False, (
            f"Warmup must use return_colbert_vecs=False to reduce startup memory, "
            f"got return_colbert_vecs={warmup_kwargs.get('return_colbert_vecs')}"
        )
        fake_model.encode = orig_encode


# ── Unit tests for _lexical_weights_to_qdrant_sparse converter ──


def _import_lexical_weights_fn():
    """Import _lexical_weights_to_qdrant_sparse with heavy deps mocked out.

    Saves and restores sys.modules["app"] so module-scoped fixtures (bge_app)
    that already imported app are not corrupted by this helper's reload.
    """
    heavy_mocks = {
        "onnxruntime": MagicMock(),
        "fastapi": MagicMock(),
        "transformers": MagicMock(),
        "prometheus_client": MagicMock(),
        "opentelemetry": MagicMock(),
        "opentelemetry.context": MagicMock(),
        "opentelemetry.propagate": MagicMock(),
    }
    # prometheus_client needs specific Counter/Gauge/Histogram constructors
    for attr in ("Counter", "Gauge", "Histogram"):
        setattr(heavy_mocks["prometheus_client"], attr, MagicMock(return_value=MagicMock()))
    heavy_mocks["prometheus_client"].make_asgi_app = MagicMock(return_value=MagicMock())

    _saved_app = sys.modules.get("app")
    with pytest.MonkeyPatch.context() as mp:
        for mod, mock in heavy_mocks.items():
            mp.setitem(sys.modules, mod, mock)
        mp.syspath_prepend(_BGE_SERVICE_DIR)
        sys.modules.pop("app", None)
        import app as _app_module

        fn = _app_module._lexical_weights_to_qdrant_sparse
        sys.modules.pop("app", None)
    # Restore original app module so module-scoped fixtures stay valid.
    if _saved_app is not None:
        sys.modules["app"] = _saved_app
    return fn


@pytest.mark.no_services
def test_lexical_weights_to_qdrant_sparse_raw_format() -> None:
    """Non-passthrough branch: {token_id: weight} dict is converted to indices+values."""
    _lexical_weights_to_qdrant_sparse = _import_lexical_weights_fn()

    raw = [{0: 0.5, 1: 0.3}]
    result = _lexical_weights_to_qdrant_sparse(raw)

    assert len(result) == 1
    item = result[0]
    assert "indices" in item
    assert "values" in item
    assert item["indices"] == [0, 1]
    assert item["values"] == [0.5, 0.3]


@pytest.mark.no_services
def test_lexical_weights_to_qdrant_sparse_passthrough() -> None:
    """Passthrough branch: already-Qdrant-format dicts are returned unchanged."""
    _lexical_weights_to_qdrant_sparse = _import_lexical_weights_fn()

    already_qdrant = [{"indices": [10, 20], "values": [0.8, 0.4]}]
    result = _lexical_weights_to_qdrant_sparse(already_qdrant)

    assert result == already_qdrant


# ── Unit tests for _onnx_sparse_to_qdrant converter ──


class Tok:
    """Minimal tokenizer stub for ``_onnx_sparse_to_qdrant`` unit tests."""

    cls_token_id: int | None = 0
    eos_token_id: int | None = 1
    pad_token_id: int | None = None
    unk_token_id: int | None = None


class TestOnnxSparseToQdrant:
    """Focused unit tests for ``_onnx_sparse_to_qdrant`` (#2209)."""

    def test_special_token_filtering(self, bge_app):
        """Special token IDs (cls=0, eos=1) must be excluded."""
        import numpy as np
        from app import _onnx_sparse_to_qdrant

        sparse = np.array([[[0.5], [0.8], [0.9]]], dtype=np.float32)
        ids = np.array([[0, 10, 1]], dtype=np.int64)
        tok = Tok()

        result = _onnx_sparse_to_qdrant(sparse, ids, tok)
        # Only token 10 should remain; cls=0 and eos=1 are special
        assert result == [{"indices": [10], "values": [0.800000011920929]}]

    def test_non_positive_weight_filtering(self, bge_app):
        """Zero and negative weights must be excluded."""
        import numpy as np
        from app import _onnx_sparse_to_qdrant

        sparse = np.array([[[0.5], [0.0], [-0.3], [0.7]]], dtype=np.float32)
        ids = np.array([[10, 11, 12, 13]], dtype=np.int64)
        tok = Tok()

        result = _onnx_sparse_to_qdrant(sparse, ids, tok)
        # Zero-weight token 11 and negative-weight token 12 must be filtered
        assert result == [{"indices": [10, 13], "values": [0.5, 0.699999988079071]}]

    def test_duplicate_token_id_keeps_max_positive(self, bge_app):
        """Duplicate token IDs must keep the max positive weight."""
        import numpy as np
        from app import _onnx_sparse_to_qdrant

        sparse = np.array([[[0.5], [0.3], [0.9]]], dtype=np.float32)
        ids = np.array([[10, 10, 10]], dtype=np.int64)
        tok = Tok()

        result = _onnx_sparse_to_qdrant(sparse, ids, tok)
        # All three positions map to token 10, keep max weight 0.9
        assert result == [{"indices": [10], "values": [0.8999999761581421]}]

    def test_acceptance_case_sparse_conversion(self, bge_app):
        """Exact acceptance case from review-fix prompt."""
        import numpy as np
        from app import _onnx_sparse_to_qdrant

        sparse = np.array([[[0.0], [0.5], [-0.2], [0.7], [0.9]]], dtype=np.float32)
        ids = np.array([[0, 10, 11, 10, 1]], dtype=np.int64)
        tok = Tok()

        result = _onnx_sparse_to_qdrant(sparse, ids, tok)
        # Expected: skip special (0=cls, 1=eos), skip zero (idx 0), skip
        # negative (-0.2 at idx 11), keep max positive for duplicate token 10 (0.7).
        assert result == [{"indices": [10], "values": [0.699999988079071]}]

    def test_multi_batch_item(self, bge_app):
        """Two batch items return one dict each."""
        import numpy as np
        from app import _onnx_sparse_to_qdrant

        sparse = np.array([[[0.5], [0.3]], [[0.1], [0.9]]], dtype=np.float32)
        ids = np.array([[10, 11], [10, 10]], dtype=np.int64)
        tok = Tok()

        result = _onnx_sparse_to_qdrant(sparse, ids, tok)
        # Item 0: tokens 10=0.5, 11=0.3
        # Item 1: token 10 appears twice → max(0.1, 0.9) = 0.9
        assert len(result) == 2
        assert result[0] == {"indices": [10, 11], "values": [0.5, 0.30000001192092896]}
        assert result[1] == {"indices": [10], "values": [0.8999999761581421]}

    def test_mixed_positive_zero_negative_with_duplicates(self, bge_app):
        """Combine special-token, non-positive, and dedup in one pass."""
        import numpy as np
        from app import _onnx_sparse_to_qdrant

        # cls=0, eos=1: special.  weights: 0(zero), -0.5(negative), +0.3, +0.7
        sparse = np.array([[[0.0], [-0.5], [0.3], [0.7]]], dtype=np.float32)
        ids = np.array([[0, 1, 10, 10]], dtype=np.int64)
        tok = Tok()

        result = _onnx_sparse_to_qdrant(sparse, ids, tok)
        # cls=0 and eos=1 are special → filtered
        # duplicate token 10 → max(0.3, 0.7) = 0.7
        assert result == [{"indices": [10], "values": [0.699999988079071]}]


# ── Unit tests for _run_encode shared helper ──


class TestRunEncode:
    """Tests for the shared ``_run_encode`` helper that backs all encode endpoints."""

    @pytest.fixture(autouse=True)
    def _patch_get_model(self, bge_app):
        """Patch app.get_model so _run_encode never tries to load a real ONNX file.

        When TestRunEncode runs after other test classes, the module-scoped
        bge_app mock may be unwound (sys.modules["app"] popped) and re-imported
        clean. The re-imported module has _onnx_session=None and a real get_model,
        so _run_encode raises FileNotFoundError. Patching in this autouse fixture
        ensures get_model returns the FakeONNXModel for every test in this class.
        """
        import sys

        if "app" in sys.modules:
            app_module = sys.modules["app"]
            app_module.get_model = bge_app["app_module"].get_model

    async def test_dense_only_returns_dense_vecs(self, bge_app):
        """_run_encode with return_dense=True returns dense_vecs in first slot."""
        from app import EncodeRequest, _run_encode

        req = EncodeRequest(texts=["hello", "world"])
        (dense, sparse, colbert), pt, failures = await _run_encode(
            req,
            encode_type="dense",
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        assert len(dense) == 2
        assert sparse == []
        assert colbert == []
        assert failures == []
        assert pt >= 0

    async def test_sparse_only_returns_lexical_weights(self, bge_app):
        """_run_encode with return_sparse=True returns lexical_weights in second slot."""
        from app import EncodeRequest, _run_encode

        req = EncodeRequest(texts=["hello"])
        (dense, sparse, colbert), _pt, _failures = await _run_encode(
            req,
            encode_type="sparse",
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        assert dense == []
        assert len(sparse) == 1
        assert "indices" in sparse[0]
        assert colbert == []

    async def test_all_invalid_fills_sentinels(self, bge_app):
        """When all texts are invalid, returns sentinel values for every slot."""
        from app import EncodeRequest, _run_encode

        req = EncodeRequest(texts=["", "   "])
        (dense, sparse, colbert), _pt, failures = await _run_encode(
            req,
            encode_type="hybrid",
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )
        assert len(failures) == 2
        # Dense: zero-vector sentinels
        assert len(dense) == 2
        assert all(v == 0.0 for v in dense[0])
        assert all(v == 0.0 for v in dense[1])
        # Sparse: empty sentinel
        assert sparse[0] == {"indices": [], "values": []}
        # ColBERT: single-token zero sentinel
        assert len(colbert[0]) == 1
        assert all(v == 0.0 for v in colbert[0][0])

    async def test_mixed_batch_partial_failure(self, bge_app):
        """Mixed valid+invalid batch: sentinel at invalid index, real vector at valid index."""
        from app import EncodeRequest, _run_encode

        req = EncodeRequest(texts=["hello", "", "world"])
        (dense, _, _), _pt, failures = await _run_encode(
            req,
            encode_type="dense",
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        assert len(failures) == 1
        assert failures[0].index == 1
        # Index 1 gets zero sentinel
        assert all(v == 0.0 for v in dense[1])
        assert len(dense[1]) == 1024
        # Valid indices have real vectors
        assert any(v != 0.0 for v in dense[0])
        assert any(v != 0.0 for v in dense[2])
