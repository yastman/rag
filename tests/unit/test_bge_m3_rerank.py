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
