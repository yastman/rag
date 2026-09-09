"""Tests for bge-m3-api /rerank endpoint.

All sys.modules mocking is fixture-scoped (no module-level pollution).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


_BGE_SERVICE_DIR = str(Path(__file__).parents[2] / "services" / "bge-m3-api")


@pytest.fixture(scope="module")
def bge_rerank_app():
    """Mock heavy deps and add bge-m3-api to sys.path for imports.
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

        mp.setitem(sys.modules, "onnxruntime", mock_ort)
        mp.setitem(sys.modules, "transformers", mock_transformers)
        mp.setitem(sys.modules, "prometheus_client", MagicMock())
        mp.syspath_prepend(_BGE_SERVICE_DIR)
        yield
        # Clean up cached service imports (not mocks — real modules imported
        # via syspath_prepend that shouldn't leak to other test files).
        for mod in ("app", "config"):
            sys.modules.pop(mod, None)


class TestRerankEndpoint:
    """Tests for ColBERT MaxSim rerank endpoint."""

    def test_rerank_request_model_validation(self, bge_rerank_app):
        """Test RerankRequest validates input."""
        from app import RerankRequest

        # Valid request
        req = RerankRequest(
            query="test query",
            documents=["doc1", "doc2"],
            top_k=2,
        )
        assert req.query == "test query"
        assert len(req.documents) == 2
        assert req.top_k == 2

    def test_rerank_response_model(self, bge_rerank_app):
        """Test RerankResponse structure."""
        from app import RerankResponse, RerankResult

        result = RerankResult(index=0, score=0.95)
        response = RerankResponse(results=[result], processing_time=0.1)

        assert response.results[0].index == 0
        assert response.results[0].score == 0.95

    def test_maxsim_score_calculation(self, bge_rerank_app):
        """Test numpy MaxSim scoring function (pure numpy, no FlagEmbedding)."""
        from app import compute_maxsim_scores

        # Mock ColBERT vectors: query (2 tokens x 4 dim), doc (3 tokens x 4 dim)
        query_vecs = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
        doc_vecs = [
            np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.float32),
            np.array([[0, 1, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=np.float32),
        ]

        scores = compute_maxsim_scores(query_vecs, doc_vecs)

        # Doc 0: query token0 matches (1.0), token1 no match (0.0) → max per dim [1.0, 0.0] → sum=1.0
        # Doc 1: query token0 no match (0.0), token1 matches (1.0) → max per dim [0.0, 1.0] → sum=1.0
        assert len(scores) == 2
        assert all(isinstance(s, float) for s in scores)


# ── Endpoint-level index preservation — deterministic fake model ───────────────


class _DeterministicColbertModel:
    """Fake BGEM3 model returning fixed ColBERT vectors for known texts.

    Deterministic MaxSim scores against query "alpha or beta":
    "alpha" → 1.0, "beta" → 0.5, unknown texts → 0.0.
    """

    def __init__(self) -> None:
        self._vec_by_text = {
            "alpha or beta": np.array([[1, 0], [0, 1]], dtype=np.float32),
            "alpha": np.array([[1, 0]], dtype=np.float32),
            "beta": np.array([[0, 0.5]], dtype=np.float32),
        }

    def encode(self, texts, **_kwargs):
        zero = np.zeros((1, 2), dtype=np.float32)
        return {"colbert_vecs": [self._vec_by_text.get(t, zero) for t in texts]}


@pytest.fixture
def bge_rerank_endpoint(bge_rerank_app, monkeypatch):
    """Install the deterministic fake model into the mocked service app module."""
    import app as app_module

    monkeypatch.setattr(
        app_module, "get_model", MagicMock(return_value=_DeterministicColbertModel())
    )
    return app_module


class TestRerankOriginalIndexPreservation:
    """Rerank response indexes must reference the original request array (#3377).

    Empty documents are filtered before scoring, but the response `index`
    must keep pointing at positions in the ORIGINAL request documents list,
    across leading/interleaved/trailing empties and ranking reorder.
    """

    async def test_rerank_preserves_original_indexes_with_leading_empty(self, bge_rerank_endpoint):
        """[empty, beta, alpha] → alpha is original index 2, beta original index 1."""
        from app import RerankRequest, rerank

        resp = await rerank(
            RerankRequest(query="alpha or beta", documents=["", "beta", "alpha"], top_k=3)
        )

        assert [r.index for r in resp.results] == [2, 1]
        assert resp.results[0].score > resp.results[1].score

    async def test_rerank_preserves_original_indexes_with_interleaved_empties(
        self, bge_rerank_endpoint
    ):
        """[beta, empty, alpha] → alpha is original index 2, beta original index 0."""
        from app import RerankRequest, rerank

        resp = await rerank(
            RerankRequest(query="alpha or beta", documents=["beta", "", "alpha"], top_k=3)
        )

        assert [r.index for r in resp.results] == [2, 0]
        assert resp.results[0].score > resp.results[1].score

    async def test_rerank_preserves_original_indexes_with_trailing_empty(self, bge_rerank_endpoint):
        """[alpha, beta, empty] → alpha is original index 0, beta original index 1."""
        from app import RerankRequest, rerank

        resp = await rerank(
            RerankRequest(query="alpha or beta", documents=["alpha", "beta", ""], top_k=3)
        )

        assert [r.index for r in resp.results] == [0, 1]
        assert resp.results[0].score > resp.results[1].score

    async def test_rerank_maps_single_kept_document_to_original_index(self, bge_rerank_endpoint):
        """[empty, alpha] → the kept document must be reported at index 1, not 0."""
        from app import RerankRequest, rerank

        resp = await rerank(RerankRequest(query="alpha or beta", documents=["", "alpha"]))

        assert [r.index for r in resp.results] == [1]
        assert resp.results[0].score == pytest.approx(1.0)

    async def test_rerank_scores_sorted_descending_with_filtered_documents(
        self, bge_rerank_endpoint
    ):
        """Scores stay descending after filtering; indexes stay in request range."""
        from app import RerankRequest, rerank

        documents = ["beta", "", "alpha", "   ", "beta"]
        resp = await rerank(RerankRequest(query="alpha or beta", documents=documents, top_k=5))

        scores = [r.score for r in resp.results]
        assert scores == sorted(scores, reverse=True)
        assert all(0 <= r.index < len(documents) for r in resp.results)

    async def test_rerank_all_empty_documents_returns_empty_results(self, bge_rerank_endpoint):
        """All-empty request → explicit empty results, no model call artifacts."""
        from app import RerankRequest, rerank

        resp = await rerank(RerankRequest(query="alpha or beta", documents=["", "   "], top_k=3))

        assert resp.results == []


# ── Mock-httpx rerank tests — no fastapi required ──────────────────────────────


class TestRerankSortOrderMocked:
    """Rerank sort-order contract using BGEM3Client with mocked httpx.

    No fastapi required — tests the client layer only.
    """

    async def test_rerank_results_sorted_by_score_descending(self) -> None:
        """Sidecar returns results in descending score order; client preserves it."""
        from unittest.mock import AsyncMock, MagicMock

        from src.services.bge_m3_client import BGEM3Client

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # Three docs; scores are not monotone in original order → client must keep sidecar order
        mock_resp.json.return_value = {
            "results": [
                {"index": 2, "score": 0.93},
                {"index": 0, "score": 0.75},
                {"index": 1, "score": 0.42},
            ],
            "processing_time": 0.12,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False

        client = BGEM3Client(base_url="http://localhost:8000")
        client._client = mock_http

        result = await client.rerank("query", ["a", "b", "c"], top_k=3)

        scores = [r["score"] for r in result.results]
        assert scores == sorted(scores, reverse=True), f"scores must be descending, got: {scores}"
        # Correct document is at the top
        assert result.results[0]["index"] == 2
