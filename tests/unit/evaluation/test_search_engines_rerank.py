# tests/unit/evaluation/test_search_engines_rerank.py
"""Tests for src/evaluation/search_engines_rerank.py."""

from unittest.mock import MagicMock, patch

import pytest


def _make_flag_embedding_mock():
    """Return a sys.modules patch dict that provides FlagEmbedding.FlagReranker."""
    mock_reranker_cls = MagicMock()
    mock_reranker_cls.return_value = MagicMock()
    mock_fe = MagicMock()
    mock_fe.FlagReranker = mock_reranker_cls
    return {"FlagEmbedding": mock_fe}, mock_reranker_cls


class TestRerankSearchEngineInit:
    """Tests for RerankSearchEngine initialization."""

    @patch("src.evaluation.search_engines_rerank.BaselineSearchEngine")
    def test_init_creates_baseline_engine(self, mock_baseline_cls):
        """Test that __init__ creates a BaselineSearchEngine."""
        from src.evaluation.search_engines_rerank import RerankSearchEngine

        fe_modules, _ = _make_flag_embedding_mock()
        with patch.dict("sys.modules", fe_modules):
            mock_model = MagicMock()
            engine = RerankSearchEngine("test_collection", mock_model)

        assert engine.baseline_engine is not None
        mock_baseline_cls.assert_called_once_with("test_collection", mock_model)

    @patch("src.evaluation.search_engines_rerank.BaselineSearchEngine")
    def test_init_raises_import_error_without_flag_embedding(self, mock_baseline_cls):
        """Test ImportError when FlagEmbedding is not installed."""
        import sys

        from src.evaluation.search_engines_rerank import RerankSearchEngine

        # Remove FlagEmbedding from sys.modules so the import inside __init__ fails
        saved = sys.modules.pop("FlagEmbedding", None)
        try:
            mock_model = MagicMock()
            with pytest.raises(ImportError, match="FlagEmbedding is not installed"):
                RerankSearchEngine("test_collection", mock_model)
        finally:
            if saved is not None:
                sys.modules["FlagEmbedding"] = saved

    @patch("src.evaluation.search_engines_rerank.BaselineSearchEngine")
    def test_init_uses_default_reranker_model(self, mock_baseline_cls):
        """Test initialization uses default BAAI/bge-reranker-v2-m3 model."""
        from src.evaluation.search_engines_rerank import RerankSearchEngine

        fe_modules, mock_reranker_cls = _make_flag_embedding_mock()
        with patch.dict("sys.modules", fe_modules):
            mock_model = MagicMock()
            RerankSearchEngine("test_collection", mock_model)

        call_args = mock_reranker_cls.call_args
        assert call_args[0][0] == "BAAI/bge-reranker-v2-m3"

    @patch("src.evaluation.search_engines_rerank.BaselineSearchEngine")
    def test_init_custom_reranker_model(self, mock_baseline_cls):
        """Test initialization with custom reranker model name."""
        from src.evaluation.search_engines_rerank import RerankSearchEngine

        fe_modules, mock_reranker_cls = _make_flag_embedding_mock()
        with patch.dict("sys.modules", fe_modules):
            mock_model = MagicMock()
            RerankSearchEngine("test_col", mock_model, reranker_model_name="custom/model")

        call_args = mock_reranker_cls.call_args
        assert call_args[0][0] == "custom/model"


class TestRerankSearchEngineSearch:
    """Tests for RerankSearchEngine.search method."""

    def _make_engine(self):
        """Create RerankSearchEngine with mocked baseline and reranker."""
        from src.evaluation.search_engines_rerank import RerankSearchEngine

        mock_baseline_instance = MagicMock()
        fe_modules, mock_reranker_cls = _make_flag_embedding_mock()
        mock_reranker_instance = MagicMock()
        mock_reranker_cls.return_value = mock_reranker_instance

        with patch("src.evaluation.search_engines_rerank.BaselineSearchEngine") as mock_bs:
            mock_bs.return_value = mock_baseline_instance
            with patch.dict("sys.modules", fe_modules):
                engine = RerankSearchEngine("test_collection", MagicMock())

        engine.baseline_engine = mock_baseline_instance
        engine.reranker = mock_reranker_instance
        return engine, mock_baseline_instance, mock_reranker_instance

    def test_search_empty_candidates_returns_empty(self):
        """Test that empty candidates from baseline returns empty list."""
        engine, mock_baseline, mock_reranker = self._make_engine()
        mock_baseline.search.return_value = []

        results = engine.search("test query", top_k=5)

        assert results == []
        mock_reranker.compute_score.assert_not_called()

    def test_search_returns_top_k_results(self):
        """Test that search returns at most top_k results."""
        engine, mock_baseline, mock_reranker = self._make_engine()
        candidates = [
            {"text": f"article {i}", "score": 0.9, "article_number": str(i)} for i in range(10)
        ]
        mock_baseline.search.return_value = candidates
        mock_reranker.compute_score.return_value = [0.9 - i * 0.05 for i in range(10)]

        results = engine.search("test query", top_k=3)

        assert len(results) == 3

    def test_search_sorts_by_rerank_score(self):
        """Test that results are sorted by reranker score descending."""
        engine, mock_baseline, mock_reranker = self._make_engine()
        candidates = [
            {"text": "article A", "score": 0.9, "article_number": "A"},
            {"text": "article B", "score": 0.8, "article_number": "B"},
            {"text": "article C", "score": 0.7, "article_number": "C"},
        ]
        mock_baseline.search.return_value = candidates
        # Reranker reverses order: C > B > A
        mock_reranker.compute_score.return_value = [0.3, 0.6, 0.9]

        results = engine.search("test query", top_k=3)

        assert results[0]["article_number"] == "C"
        assert results[1]["article_number"] == "B"
        assert results[2]["article_number"] == "A"

    def test_search_replaces_score_with_rerank_score(self):
        """Test that candidate scores are replaced by reranker scores."""
        engine, mock_baseline, mock_reranker = self._make_engine()
        candidates = [{"text": "article", "score": 0.5, "article_number": "1"}]
        mock_baseline.search.return_value = candidates
        mock_reranker.compute_score.return_value = [0.87]

        results = engine.search("test query", top_k=5)

        assert len(results) == 1
        assert abs(results[0]["score"] - 0.87) < 1e-6

    def test_search_passes_query_pairs_to_reranker(self):
        """Test that search passes (query, text) pairs to reranker."""
        engine, mock_baseline, mock_reranker = self._make_engine()
        candidates = [
            {"text": "first passage", "score": 0.9, "article_number": "1"},
            {"text": "second passage", "score": 0.8, "article_number": "2"},
        ]
        mock_baseline.search.return_value = candidates
        mock_reranker.compute_score.return_value = [0.9, 0.8]

        engine.search("my query", top_k=5, retrieval_top_k=50)

        call_args = mock_reranker.compute_score.call_args
        pairs = call_args[0][0]
        assert pairs == [["my query", "first passage"], ["my query", "second passage"]]
        assert call_args[1].get("normalize") is True


class TestCreateRerankSearchEngine:
    """Tests for create_rerank_search_engine factory function."""

    @patch("src.evaluation.search_engines_rerank.BaselineSearchEngine")
    def test_factory_returns_rerank_engine(self, mock_baseline_cls):
        """Test that factory returns RerankSearchEngine instance."""
        from src.evaluation.search_engines_rerank import (
            RerankSearchEngine,
            create_rerank_search_engine,
        )

        fe_modules, _ = _make_flag_embedding_mock()
        with patch.dict("sys.modules", fe_modules):
            mock_model = MagicMock()
            engine = create_rerank_search_engine("test_collection", mock_model)

        assert isinstance(engine, RerankSearchEngine)

    @patch("src.evaluation.search_engines_rerank.BaselineSearchEngine")
    def test_factory_passes_custom_reranker_model(self, mock_baseline_cls):
        """Test that factory forwards custom reranker model name."""
        from src.evaluation.search_engines_rerank import create_rerank_search_engine

        fe_modules, mock_reranker_cls = _make_flag_embedding_mock()
        with patch.dict("sys.modules", fe_modules):
            mock_model = MagicMock()
            create_rerank_search_engine("col", mock_model, reranker_model="custom/reranker")

        call_args = mock_reranker_cls.call_args
        assert call_args[0][0] == "custom/reranker"
