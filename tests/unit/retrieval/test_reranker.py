"""Unit tests for src/retrieval/reranker.py.

Note: sentence_transformers is mocked in conftest.py to avoid slow model loading.
The reranker module is provided via fixture to ensure fresh import with mock.
"""

from unittest.mock import MagicMock, patch

import numpy as np


class TestGetCrossEncoder:
    """Test get_cross_encoder singleton function."""

    def test_get_cross_encoder_creates_new_instance(self, reranker, mock_cross_encoder):
        """Test that first call creates a new CrossEncoder instance."""
        result = reranker.get_cross_encoder()

        mock_cross_encoder["class"].assert_called_once_with(
            "cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512
        )
        assert result == mock_cross_encoder["encoder"]

    def test_get_cross_encoder_returns_singleton(self, reranker, mock_cross_encoder):
        """Test that subsequent calls return same instance."""
        result1 = reranker.get_cross_encoder()
        result2 = reranker.get_cross_encoder()

        # Should only create once
        mock_cross_encoder["class"].assert_called_once()
        assert result1 is result2

    def test_get_cross_encoder_custom_model_name(self, reranker, mock_cross_encoder):
        """Test creating encoder with custom model name."""
        result = reranker.get_cross_encoder("custom/model")

        mock_cross_encoder["class"].assert_called_once_with("custom/model", max_length=512)
        assert result == mock_cross_encoder["encoder"]


class TestRerankResults:
    """Test rerank_results function."""

    def test_rerank_empty_results(self, reranker, mock_cross_encoder):
        """Test reranking empty results returns empty list."""
        result = reranker.rerank_results("query", [])
        assert result == []

    def test_rerank_results_success(self, reranker, mock_cross_encoder):
        """Test successful reranking of results."""
        # Return scores: first result is worst, third is best
        mock_cross_encoder["encoder"].predict.return_value = np.array([0.3, 0.5, 0.9])

        results = [
            {"text": "Doc 1", "score": 0.8},
            {"text": "Doc 2", "score": 0.7},
            {"text": "Doc 3", "score": 0.6},
        ]

        reranked = reranker.rerank_results("test query", results, top_k=3)

        # Should be sorted by rerank score (descending)
        assert reranked[0]["text"] == "Doc 3"  # Score 0.9
        assert reranked[1]["text"] == "Doc 2"  # Score 0.5
        assert reranked[2]["text"] == "Doc 1"  # Score 0.3

        # Verify scores were updated
        assert reranked[0]["rerank_score"] == 0.9
        assert reranked[0]["original_score"] == 0.6

    def test_rerank_results_preserves_remaining(self, reranker, mock_cross_encoder):
        """Test that results beyond top_k are preserved unchanged."""
        mock_cross_encoder["encoder"].predict.return_value = np.array([0.5, 0.8])  # Only for top 2

        results = [
            {"text": "Doc 1", "score": 0.9},
            {"text": "Doc 2", "score": 0.8},
            {"text": "Doc 3", "score": 0.7},
            {"text": "Doc 4", "score": 0.6},
        ]

        reranked = reranker.rerank_results("query", results, top_k=2)

        # First 2 should be reranked
        assert len(reranked) == 4

        # Last 2 should be unchanged (appended after reranked)
        assert reranked[2]["text"] == "Doc 3"
        assert reranked[3]["text"] == "Doc 4"
        assert "rerank_score" not in reranked[2]
        assert "rerank_score" not in reranked[3]

    def test_rerank_results_creates_query_document_pairs(self, reranker, mock_cross_encoder):
        """Test that correct query-document pairs are created."""
        mock_cross_encoder["encoder"].predict.return_value = np.array([0.5, 0.6])

        results = [
            {"text": "First document", "score": 0.9},
            {"text": "Second document", "score": 0.8},
        ]

        reranker.rerank_results("my query", results, top_k=2)

        # Verify pairs passed to predict
        mock_cross_encoder["encoder"].predict.assert_called_once()
        pairs = mock_cross_encoder["encoder"].predict.call_args[0][0]
        assert pairs == [("my query", "First document"), ("my query", "Second document")]

    def test_rerank_results_handles_exception(self, reranker, mock_cross_encoder):
        """Test that exceptions return original results."""
        mock_cross_encoder["encoder"].predict.side_effect = RuntimeError("Model error")

        results = [
            {"text": "Doc 1", "score": 0.9},
            {"text": "Doc 2", "score": 0.8},
        ]

        reranked = reranker.rerank_results("query", results, top_k=2)

        # Should return original results unchanged
        assert reranked == results
        assert "rerank_score" not in reranked[0]

    def test_rerank_results_default_top_k(self, reranker, mock_cross_encoder):
        """Test default top_k is 5."""
        mock_cross_encoder["encoder"].predict.return_value = np.array([0.5] * 5)

        results = [{"text": f"Doc {i}", "score": 0.9 - i * 0.1} for i in range(10)]

        reranker.rerank_results("query", results)

        # Should have created 5 pairs
        pairs = mock_cross_encoder["encoder"].predict.call_args[0][0]
        assert len(pairs) == 5

    def test_rerank_results_fewer_than_top_k(self, reranker, mock_cross_encoder):
        """Test reranking when results < top_k."""
        mock_cross_encoder["encoder"].predict.return_value = np.array([0.8, 0.6])

        results = [
            {"text": "Doc 1", "score": 0.5},
            {"text": "Doc 2", "score": 0.4},
        ]

        reranked = reranker.rerank_results("query", results, top_k=5)

        # Should work fine with fewer results
        assert len(reranked) == 2
        assert reranked[0]["rerank_score"] == 0.8
        assert reranked[1]["rerank_score"] == 0.6

    def test_rerank_results_score_conversion_to_float(self, reranker, mock_cross_encoder):
        """Test that scores are converted to float."""
        # Return numpy-like values (simulating numpy array output)
        mock_cross_encoder["encoder"].predict.return_value = np.array([0.75])

        results = [{"text": "Doc", "score": 0.5}]

        reranked = reranker.rerank_results("query", results, top_k=1)

        # Score should be Python float
        assert isinstance(reranked[0]["score"], float)
        assert isinstance(reranked[0]["rerank_score"], float)


class TestClearCrossEncoder:
    """Test clear_cross_encoder function."""

    def test_clear_cross_encoder_when_none(self, reranker, mock_cross_encoder):
        """Test clearing when no encoder exists."""
        reranker._cross_encoder = None

        # Should not raise
        reranker.clear_cross_encoder()

        assert reranker._cross_encoder is None

    def test_clear_cross_encoder_when_exists(self, reranker, mock_cross_encoder):
        """Test clearing existing encoder."""
        reranker._cross_encoder = mock_cross_encoder["encoder"]

        # Avoid collecting unrelated global objects under strict warning mode.
        with patch("gc.collect", return_value=0):
            reranker.clear_cross_encoder()

        assert reranker._cross_encoder is None

    def test_clear_cross_encoder_allows_recreation(self, reranker, mock_cross_encoder):
        """Test that encoder can be recreated after clearing."""
        mock_encoder1 = MagicMock()
        mock_encoder2 = MagicMock()

        mock_cross_encoder["class"].side_effect = [mock_encoder1, mock_encoder2]

        encoder1 = reranker.get_cross_encoder()
        assert encoder1 == mock_encoder1

        # Avoid collecting unrelated global objects under strict warning mode.
        with patch("gc.collect", return_value=0):
            reranker.clear_cross_encoder()

        encoder2 = reranker.get_cross_encoder()
        assert encoder2 == mock_encoder2
        assert encoder2 is not encoder1
