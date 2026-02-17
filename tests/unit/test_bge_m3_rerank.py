"""Tests for bge-m3-api /rerank endpoint.

All sys.modules mocking is fixture-scoped (no module-level pollution).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


pytest.importorskip("fastapi", reason="fastapi not installed (voice extra)")
pytestmark = pytest.mark.requires_extras


_BGE_SERVICE_DIR = str(Path(__file__).parents[2] / "services" / "bge-m3-api")


@pytest.fixture(scope="module")
def bge_rerank_app():
    """Mock heavy deps and add bge-m3-api to sys.path for imports."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "FlagEmbedding", MagicMock())
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
        """Test MaxSim scoring function."""
        from app import compute_maxsim_scores

        # Mock ColBERT vectors: query (2 tokens x 4 dim), doc (3 tokens x 4 dim)
        query_vecs = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
        doc_vecs = [
            np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.float32),
            np.array([[0, 1, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=np.float32),
        ]

        scores = compute_maxsim_scores(query_vecs, doc_vecs)

        # Doc 0: token0 matches perfectly (1.0), token1 no match (0.0) → sum=1.0
        # Doc 1: token0 no match (0.0), token1 matches (1.0) → sum=1.0
        assert len(scores) == 2
        assert all(isinstance(s, float) for s in scores)
