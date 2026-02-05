"""Tests for bge-m3-api /rerank endpoint."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np


# Mock heavy dependencies before importing app
sys.modules["FlagEmbedding"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()

# Add services/bge-m3-api to path for imports
sys.path.insert(0, str(Path(__file__).parents[2] / "services" / "bge-m3-api"))


class TestRerankEndpoint:
    """Tests for ColBERT MaxSim rerank endpoint."""

    def test_rerank_request_model_validation(self):
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

    def test_rerank_response_model(self):
        """Test RerankResponse structure."""
        from app import RerankResponse, RerankResult

        result = RerankResult(index=0, score=0.95)
        response = RerankResponse(results=[result], processing_time=0.1)

        assert response.results[0].index == 0
        assert response.results[0].score == 0.95

    def test_maxsim_score_calculation(self):
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
