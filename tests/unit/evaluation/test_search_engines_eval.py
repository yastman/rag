# tests/unit/evaluation/test_search_engines_eval.py
"""Tests for src/evaluation/search_engines.py (evaluation module)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from qdrant_client import models


class TestConvertToPythonTypes:
    """Tests for convert_to_python_types helper function."""

    def test_convert_numpy_array_to_list(self):
        from src.evaluation.search_engines import convert_to_python_types

        result = convert_to_python_types(np.array([1.0, 2.0, 3.0]))
        assert result == [1.0, 2.0, 3.0]
        assert isinstance(result, list)

    @pytest.mark.parametrize(
        ("np_val", "expected", "expected_type"),
        [
            (np.float32(3.14), 3.14, float),
            (np.float64(3.14159), 3.14159, float),
            (np.int32(42), 42, int),
            (np.int64(42), 42, int),
        ],
    )
    def test_convert_numpy_scalar(self, np_val, expected, expected_type):
        from src.evaluation.search_engines import convert_to_python_types

        result = convert_to_python_types(np_val)
        assert result == pytest.approx(expected, rel=1e-5)
        assert isinstance(result, expected_type)

    def test_convert_nested_dict(self):
        """Test conversion of nested dict with numpy types."""
        from src.evaluation.search_engines import convert_to_python_types

        data = {
            "values": np.array([1.0, 2.0]),
            "score": np.float32(0.95),
            "count": np.int32(5),
        }
        result = convert_to_python_types(data)

        assert result["values"] == [1.0, 2.0]
        assert isinstance(result["score"], float)
        assert isinstance(result["count"], int)

    def test_convert_nested_list(self):
        """Test conversion of nested list with numpy types."""
        from src.evaluation.search_engines import convert_to_python_types

        data = [np.float32(1.0), np.array([2.0, 3.0]), "string"]
        result = convert_to_python_types(data)

        assert isinstance(result[0], float)
        assert result[1] == [2.0, 3.0]
        assert result[2] == "string"

    def test_convert_python_types_unchanged(self):
        """Test that Python types are unchanged."""
        from src.evaluation.search_engines import convert_to_python_types

        data = {
            "string": "text",
            "int": 42,
            "float": 3.14,
            "list": [1, 2, 3],
        }
        result = convert_to_python_types(data)

        assert result == data


class TestSearchEngineBase:
    """Tests for SearchEngine base class."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_search_engine_init(self, mock_settings_cls, mock_qdrant):
        """Test SearchEngine initialization."""
        from src.evaluation.search_engines import SearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        # SearchEngine is abstract, so we test via concrete implementation
        # Just verify the import works
        assert SearchEngine is not None

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_extract_article_number(self, mock_settings_cls, mock_qdrant):
        """Test _extract_article_number helper."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        # Create mock model
        mock_model = MagicMock()

        engine = BaselineSearchEngine("test_collection", mock_model)

        payload = {"article_number": "115"}
        result = engine._extract_article_number(payload)
        assert result == "115"

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_extract_article_number_missing(self, mock_settings_cls, mock_qdrant):
        """Test _extract_article_number with missing field."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = BaselineSearchEngine("test_collection", mock_model)

        payload = {}
        result = engine._extract_article_number(payload)
        assert result == ""


class TestBaselineSearchEngine:
    """Tests for BaselineSearchEngine."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_init(self, mock_settings_cls, mock_qdrant):
        """Test BaselineSearchEngine initialization."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = BaselineSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"
        assert engine.embedding_model == mock_model

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_search_generates_embedding(self, mock_settings_cls, mock_qdrant):
        """Test that search generates dense embedding."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {"dense_vecs": np.array([0.1, 0.2, 0.3])}

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = BaselineSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        mock_model.encode.assert_called_once_with(
            "test query",
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_search_returns_results(self, mock_settings_cls, mock_qdrant):
        """Test that search returns formatted results."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {"dense_vecs": np.array([0.1, 0.2, 0.3])}

        # Create mock search result using SDK point format
        mock_point = MagicMock()
        mock_point.id = 1
        mock_point.score = 0.95
        mock_point.payload = {
            "article_number": "115",
            "text": "Sample article text for testing",
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = [mock_point]
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = BaselineSearchEngine("test_collection", mock_model)
        results = engine.search("test query", top_k=5)

        assert len(results) == 1
        assert results[0]["article_number"] == "115"
        assert results[0]["score"] == 0.95

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_search_calls_client(self, mock_settings_cls, mock_qdrant):
        """Test that baseline search calls client.query_points with correct params."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {"dense_vecs": np.array([0.1, 0.2, 0.3])}

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = BaselineSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["limit"] == 5
        assert call_kwargs["with_payload"] is True


class TestHybridSearchEngine:
    """Tests for HybridSearchEngine."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_init(self, mock_settings_cls, mock_qdrant):
        """Test HybridSearchEngine initialization."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = HybridSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"
        assert engine.embedding_model == mock_model

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_generates_all_embeddings(self, mock_settings_cls, mock_qdrant):
        """Test that hybrid search generates dense and sparse embeddings."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2, 0.3]),
            "lexical_weights": {"100": 0.5, "200": 0.8},
            "colbert_vecs": np.array([[0.1, 0.2], [0.3, 0.4]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        mock_model.encode.assert_called_once_with(
            "test query",
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_uses_query_points(self, mock_settings_cls, mock_qdrant):
        """Test that hybrid search uses SDK query_points."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5, "200": 0.8},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["collection_name"] == "test_collection"
        assert "prefetch" in call_kwargs

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_uses_rrf_fusion(self, mock_settings_cls, mock_qdrant):
        """Test that hybrid search uses RRF fusion."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Verify query_points was called with FusionQuery(RRF)
        call_kwargs = mock_client.query_points.call_args[1]
        query = call_kwargs["query"]
        assert isinstance(query, models.FusionQuery)
        assert query.fusion == models.Fusion.RRF

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_handles_scipy_sparse(self, mock_settings_cls, mock_qdrant):
        """Test that hybrid search handles scipy sparse format."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        # Create mock scipy-like sparse object
        mock_sparse = MagicMock()
        mock_sparse.indices = np.array([100, 200, 300])
        mock_sparse.values = np.array([0.5, 0.8, 0.3])

        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": mock_sparse,
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Should not raise exception
        mock_client.query_points.assert_called_once()

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_returns_results(self, mock_settings_cls, mock_qdrant):
        """Test parsing response from query_points."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_point = MagicMock()
        mock_point.id = 1
        mock_point.score = 0.95
        mock_point.payload = {"article_number": "115", "text": "Test text"}

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = [mock_point]
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        results = engine.search("test", top_k=5)

        assert len(results) == 1
        assert results[0]["article_number"] == "115"


class TestHybridDBSFColBERTSearchEngine:
    """Tests for HybridDBSFColBERTSearchEngine."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_dbsf_colbert_init(self, mock_settings_cls, mock_qdrant):
        """Test HybridDBSFColBERTSearchEngine initialization."""
        from src.evaluation.search_engines import HybridDBSFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = HybridDBSFColBERTSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_dbsf_colbert_uses_dbsf_fusion(self, mock_settings_cls, mock_qdrant):
        """Test that DBSF+ColBERT search uses DBSF fusion."""
        from src.evaluation.search_engines import HybridDBSFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridDBSFColBERTSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Verify query_points was called
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]

        # Verify uses colbert for reranking
        assert call_kwargs["using"] == "colbert"

        # Verify nested prefetch with DBSF fusion
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 1
        inner_prefetch = prefetch[0]
        assert isinstance(inner_prefetch, models.Prefetch)
        assert isinstance(inner_prefetch.query, models.FusionQuery)
        assert inner_prefetch.query.fusion == models.Fusion.DBSF

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_dbsf_colbert_uses_colbert_for_rerank(self, mock_settings_cls, mock_qdrant):
        """Test that DBSF+ColBERT uses ColBERT for final reranking."""
        from src.evaluation.search_engines import HybridDBSFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridDBSFColBERTSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["using"] == "colbert"


class TestHybridRRFColBERTSearchEngine:
    """Tests for HybridRRFColBERTSearchEngine."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_rrf_colbert_init(self, mock_settings_cls, mock_qdrant):
        """Test HybridRRFColBERTSearchEngine initialization."""
        from src.evaluation.search_engines import HybridRRFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = HybridRRFColBERTSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_rrf_colbert_uses_rrf_fusion(self, mock_settings_cls, mock_qdrant):
        """Test that RRF+ColBERT search uses RRF fusion."""
        from src.evaluation.search_engines import HybridRRFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridRRFColBERTSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        call_kwargs = mock_client.query_points.call_args[1]

        # Verify nested prefetch with RRF fusion
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 1
        inner_prefetch = prefetch[0]
        assert isinstance(inner_prefetch, models.Prefetch)
        assert isinstance(inner_prefetch.query, models.FusionQuery)
        assert inner_prefetch.query.fusion == models.Fusion.RRF


class TestCreateSearchEngine:
    """Tests for create_search_engine factory function."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_create_baseline_engine(self, mock_settings_cls, mock_qdrant):
        """Test creating baseline engine."""
        from src.evaluation.search_engines import (
            BaselineSearchEngine,
            create_search_engine,
        )

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = create_search_engine("baseline", "test_collection", mock_model)

        assert isinstance(engine, BaselineSearchEngine)

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_create_hybrid_engine(self, mock_settings_cls, mock_qdrant):
        """Test creating hybrid engine."""
        from src.evaluation.search_engines import (
            HybridSearchEngine,
            create_search_engine,
        )

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = create_search_engine("hybrid", "test_collection", mock_model)

        assert isinstance(engine, HybridSearchEngine)

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_create_dbsf_colbert_engine(self, mock_settings_cls, mock_qdrant):
        """Test creating DBSF+ColBERT engine."""
        from src.evaluation.search_engines import (
            HybridDBSFColBERTSearchEngine,
            create_search_engine,
        )

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = create_search_engine("dbsf_colbert", "test_collection", mock_model)

        assert isinstance(engine, HybridDBSFColBERTSearchEngine)

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_create_rrf_colbert_engine(self, mock_settings_cls, mock_qdrant):
        """Test creating RRF+ColBERT engine."""
        from src.evaluation.search_engines import (
            HybridRRFColBERTSearchEngine,
            create_search_engine,
        )

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = create_search_engine("rrf_colbert", "test_collection", mock_model)

        assert isinstance(engine, HybridRRFColBERTSearchEngine)

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_create_unknown_engine_raises_error(self, mock_settings_cls, mock_qdrant):
        """Test that unknown engine type raises ValueError."""
        from src.evaluation.search_engines import create_search_engine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()

        with pytest.raises(ValueError, match="Unknown engine type"):
            create_search_engine("unknown_engine", "test_collection", mock_model)


class TestSearchEngineResponseParsing:
    """Tests for response parsing in search engines."""

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_parse_query_points_response(self, mock_settings_cls, mock_qdrant):
        """Test parsing response from query_points."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_point = MagicMock()
        mock_point.id = 1
        mock_point.score = 0.95
        mock_point.payload = {"article_number": "115", "text": "Test text"}

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = [mock_point]
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        results = engine.search("test", top_k=5)

        assert len(results) == 1
        assert results[0]["article_number"] == "115"

    @patch("src.evaluation.search_engines.QdrantClient")
    @patch("src.evaluation.search_engines.Settings")
    def test_parse_empty_result(self, mock_settings_cls, mock_qdrant):
        """Test parsing empty result."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response
        mock_qdrant.return_value = mock_client

        engine = HybridSearchEngine("test_collection", mock_model)
        results = engine.search("test", top_k=5)

        assert len(results) == 0


class TestLexicalWeightsToSparse:
    """Tests for _lexical_weights_to_sparse helper."""

    def test_dict_format(self):
        """Test converting dict lexical weights to SparseVector."""
        from src.evaluation.search_engines import _lexical_weights_to_sparse

        weights = {"100": 0.5, "200": 0.8, "300": 0.3}
        sparse = _lexical_weights_to_sparse(weights)

        assert isinstance(sparse, models.SparseVector)
        assert sparse.indices == [100, 200, 300]
        assert sparse.values == [0.5, 0.8, 0.3]

    def test_scipy_sparse_format(self):
        """Test converting scipy sparse format to SparseVector."""
        from src.evaluation.search_engines import _lexical_weights_to_sparse

        mock_sparse = MagicMock()
        mock_sparse.indices = np.array([100, 200])
        mock_sparse.values = np.array([0.5, 0.8])

        sparse = _lexical_weights_to_sparse(mock_sparse)

        assert isinstance(sparse, models.SparseVector)
        assert sparse.indices == [100, 200]
        assert sparse.values == pytest.approx([0.5, 0.8])
