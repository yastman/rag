"""Unit tests for src/retrieval/search_engines.py."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from qdrant_client import models

import src.retrieval.search_engines as search_engines
from src.config.constants import SearchEngine
from src.retrieval.search_engine_shared import lexical_weights_to_sparse as shared_sparse
from src.retrieval.search_engines import (
    BaselineSearchEngine,
    DBSFColBERTSearchEngine,
    HybridRRFColBERTSearchEngine,
    HybridRRFSearchEngine,
    SearchResult,
    convert_to_python_types,
    create_search_engine,
    lexical_weights_to_sparse,
)
from src.utils.serialization import convert_to_python_types as shared_convert


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test basic SearchResult creation."""
        result = SearchResult(
            article_number="115",
            text="Sample text",
            score=0.95,
            metadata={"chapter": "I"},
        )

        assert result.article_number == "115"
        assert result.text == "Sample text"
        assert result.score == 0.95
        assert result.metadata == {"chapter": "I"}

    def test_search_result_empty_metadata(self):
        """Test SearchResult with empty metadata."""
        result = SearchResult(
            article_number="1",
            text="Text",
            score=0.5,
            metadata={},
        )

        assert result.metadata == {}


class TestConvertToPythonTypes:
    """Test numpy type conversion."""

    def test_retrieval_module_reexports_shared_helper(self):
        """Test helper is re-exported from shared serialization module."""
        assert convert_to_python_types is shared_convert

    def test_convert_numpy_array(self):
        """Test numpy array to list conversion."""
        arr = np.array([1.0, 2.0, 3.0])
        result = convert_to_python_types(arr)

        assert result == [1.0, 2.0, 3.0]
        assert isinstance(result, list)

    def test_convert_numpy_float32(self):
        """Test numpy float32 to Python float."""
        val = np.float32(3.14)
        result = convert_to_python_types(val)

        assert result == pytest.approx(3.14, rel=1e-5)
        assert isinstance(result, float)

    def test_convert_numpy_float64(self):
        """Test numpy float64 to Python float."""
        val = np.float64(3.14159)
        result = convert_to_python_types(val)

        assert result == pytest.approx(3.14159)
        assert isinstance(result, float)

    def test_convert_numpy_int32(self):
        """Test numpy int32 to Python int."""
        val = np.int32(42)
        result = convert_to_python_types(val)

        assert result == 42
        assert isinstance(result, int)

    def test_convert_numpy_int64(self):
        """Test numpy int64 to Python int."""
        val = np.int64(42)
        result = convert_to_python_types(val)

        assert result == 42
        assert isinstance(result, int)

    def test_convert_nested_dict(self):
        """Test conversion of nested dict with numpy types."""
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
        data = [np.float32(1.0), np.array([2.0, 3.0]), "string"]
        result = convert_to_python_types(data)

        assert isinstance(result[0], float)
        assert result[1] == [2.0, 3.0]
        assert result[2] == "string"

    def test_convert_python_types_unchanged(self):
        """Test that Python types are unchanged."""
        data = {
            "string": "text",
            "int": 42,
            "float": 3.14,
            "list": [1, 2, 3],
        }
        result = convert_to_python_types(data)

        assert result == data


class TestBaselineSearchEngine:
    """Test BaselineSearchEngine."""

    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_baseline_get_name(self, mock_settings_cls, mock_qdrant):
        """Test get_name returns 'baseline'."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        engine = BaselineSearchEngine(mock_settings)

        assert engine.get_name() == "baseline"

    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_baseline_search_default_threshold(self, mock_settings_cls, mock_qdrant):
        """Test default score threshold is 0.5."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.query_points.return_value = MagicMock(points=[])
        mock_qdrant.return_value = mock_client

        engine = BaselineSearchEngine(mock_settings)
        engine.search([0.1, 0.2, 0.3], top_k=5)

        # Check that query_points was called with default threshold 0.5
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["score_threshold"] == 0.5

    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_baseline_search_custom_threshold(self, mock_settings_cls, mock_qdrant):
        """Test custom score threshold."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.query_points.return_value = MagicMock(points=[])
        mock_qdrant.return_value = mock_client

        engine = BaselineSearchEngine(mock_settings)
        engine.search([0.1, 0.2, 0.3], top_k=5, score_threshold=0.7)

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["score_threshold"] == 0.7

    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_baseline_search_returns_results(self, mock_settings_cls, mock_qdrant):
        """Test that search returns formatted results."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        # Create mock search result
        mock_result = MagicMock()
        mock_result.payload = {
            "metadata": {"article_number": "115"},
            "page_content": "Sample text",
        }
        mock_result.score = 0.95

        mock_client = MagicMock()
        mock_client.query_points.return_value = MagicMock(points=[mock_result])
        mock_qdrant.return_value = mock_client

        engine = BaselineSearchEngine(mock_settings)
        results = engine.search([0.1, 0.2, 0.3], top_k=5)

        assert len(results) == 1
        assert results[0].article_number == "115"
        assert results[0].text == "Sample text"
        assert results[0].score == 0.95


class TestHybridRRFSearchEngine:
    """Test HybridRRFSearchEngine."""

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_hybrid_get_name(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test get_name returns 'hybrid_rrf'."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        engine = HybridRRFSearchEngine(mock_settings)

        assert engine.get_name() == "hybrid_rrf"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_hybrid_search_with_embedding(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test search with pre-computed embedding uses dense-only via query_points."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.query_points.return_value = MagicMock(points=[])
        mock_qdrant.return_value = mock_client

        engine = HybridRRFSearchEngine(mock_settings)
        engine.search([0.1, 0.2, 0.3], top_k=5)

        # Should call dense-only query_points when pre-computed embedding provided
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["using"] == "dense"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_hybrid_search_uses_query_points(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that hybrid search uses SDK query_points with prefetch."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.collection_name = "test_collection"
        mock_settings.get_collection_name.return_value = "test_collection"
        mock_settings_cls.return_value = mock_settings

        # Mock embedding model
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2, 0.3]),
            "lexical_weights": {"100": 0.5, "200": 0.8},
        }
        mock_bge.return_value = mock_model

        # Mock query_points response
        mock_point = MagicMock()
        mock_point.payload = {
            "metadata": {"article_number": "115"},
            "page_content": "Test content",
        }
        mock_point.score = 0.95

        mock_client = MagicMock()
        mock_query_response = MagicMock()
        mock_query_response.points = [mock_point]
        mock_client.query_points.return_value = mock_query_response
        mock_qdrant.return_value = mock_client

        engine = HybridRRFSearchEngine(mock_settings)
        results = engine.search("test query", top_k=5)

        # Verify query_points was called (not httpx)
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]

        # Verify prefetch structure
        assert "prefetch" in call_kwargs
        assert call_kwargs["collection_name"] == "test_collection"

        # Verify results
        assert len(results) == 1
        assert results[0].article_number == "115"
        assert results[0].score == 0.95


class TestHybridRRFColBERTSearchEngine:
    """Test HybridRRFColBERTSearchEngine."""

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_colbert_get_name(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test get_name returns 'hybrid_rrf_colbert'."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        engine = HybridRRFColBERTSearchEngine(mock_settings)

        assert engine.get_name() == "hybrid_rrf_colbert"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_colbert_search_with_embedding(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test search with pre-computed embedding uses dense-only via query_points."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        mock_client = MagicMock()
        mock_client.query_points.return_value = MagicMock(points=[])
        mock_qdrant.return_value = mock_client

        engine = HybridRRFColBERTSearchEngine(mock_settings)
        engine.search([0.1, 0.2, 0.3], top_k=5)

        # Should call dense-only query_points when pre-computed embedding provided
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["using"] == "dense"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_colbert_search_uses_nested_prefetch(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that ColBERT search uses SDK with nested prefetch for 3-stage query."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.collection_name = "test_collection"
        mock_settings_cls.return_value = mock_settings

        # Mock embedding model with ColBERT vectors
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2, 0.3]),
            "lexical_weights": {"100": 0.5, "200": 0.8},
            "colbert_vecs": np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]),
        }
        mock_bge.return_value = mock_model

        # Mock query_points response
        mock_point = MagicMock()
        mock_point.payload = {
            "article_number": "115",
            "page_content": "Test content",
        }
        mock_point.score = 0.95

        mock_client = MagicMock()
        mock_query_response = MagicMock()
        mock_query_response.points = [mock_point]
        mock_client.query_points.return_value = mock_query_response
        mock_qdrant.return_value = mock_client

        engine = HybridRRFColBERTSearchEngine(mock_settings)
        results = engine.search("test query", top_k=5)

        # Verify query_points was called with nested prefetch
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]

        # Verify nested prefetch structure (outer prefetch contains inner prefetch with RRF)
        assert "prefetch" in call_kwargs
        assert call_kwargs["using"] == "colbert"  # Final stage uses ColBERT

        assert len(results) == 1
        assert results[0].score == 0.95


class TestDBSFColBERTSearchEngine:
    """Test DBSFColBERTSearchEngine."""

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_dbsf_get_name(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test get_name returns 'dbsf_colbert'."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.collection_name = "test"
        mock_settings_cls.return_value = mock_settings

        engine = DBSFColBERTSearchEngine(mock_settings)

        assert engine.get_name() == "dbsf_colbert"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_dbsf_search_uses_dbsf_fusion(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that DBSF search uses DBSF fusion instead of RRF."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.collection_name = "test_collection"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2, 0.3]),
            "lexical_weights": {"100": 0.5},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }
        mock_bge.return_value = mock_model

        mock_point = MagicMock()
        mock_point.payload = {"page_content": "Test"}
        mock_point.score = 0.9

        mock_client = MagicMock()
        mock_query_response = MagicMock()
        mock_query_response.points = [mock_point]
        mock_client.query_points.return_value = mock_query_response
        mock_qdrant.return_value = mock_client

        engine = DBSFColBERTSearchEngine(mock_settings)
        engine.search("test query", top_k=5)

        # Verify query_points was called with DBSF fusion
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]

        # Verify nested prefetch with DBSF fusion
        assert "prefetch" in call_kwargs
        assert call_kwargs["using"] == "colbert"


class TestCreateSearchEngine:
    """Test search engine factory function."""

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_create_baseline_engine(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test creating baseline engine."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.search_engine = SearchEngine.BASELINE
        mock_settings_cls.return_value = mock_settings

        engine = create_search_engine(SearchEngine.BASELINE, mock_settings)

        assert isinstance(engine, BaselineSearchEngine)
        assert engine.get_name() == "baseline"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_create_hybrid_rrf_engine(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test creating hybrid RRF engine."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        engine = create_search_engine(SearchEngine.HYBRID_RRF, mock_settings)

        assert isinstance(engine, HybridRRFSearchEngine)
        assert engine.get_name() == "hybrid_rrf"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_create_hybrid_rrf_colbert_engine(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test creating hybrid RRF ColBERT engine."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        engine = create_search_engine(SearchEngine.HYBRID_RRF_COLBERT, mock_settings)

        assert isinstance(engine, HybridRRFColBERTSearchEngine)
        assert engine.get_name() == "hybrid_rrf_colbert"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_create_dbsf_colbert_engine(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test creating DBSF ColBERT engine."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings_cls.return_value = mock_settings

        engine = create_search_engine(SearchEngine.DBSF_COLBERT, mock_settings)

        assert isinstance(engine, DBSFColBERTSearchEngine)
        assert engine.get_name() == "dbsf_colbert"

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_create_default_engine(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that default engine is HybridRRFColBERT."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.search_engine = SearchEngine.HYBRID_RRF_COLBERT
        mock_settings_cls.return_value = mock_settings

        engine = create_search_engine(settings=mock_settings)

        assert isinstance(engine, HybridRRFColBERTSearchEngine)

    @patch.object(search_engines, "get_bge_m3_model")
    @patch.object(search_engines, "QdrantClient")
    @patch.object(search_engines, "Settings")
    def test_create_uses_settings_engine_type(self, mock_settings_cls, mock_qdrant, mock_bge):
        """Test that factory uses settings.search_engine when type not provided."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.search_engine = SearchEngine.BASELINE
        mock_settings_cls.return_value = mock_settings

        engine = create_search_engine(settings=mock_settings)

        assert isinstance(engine, BaselineSearchEngine)


class TestSparseVectorConversion:
    """Test sparse vector conversion to Qdrant models."""

    def test_retrieval_module_reexports_shared_sparse_helper(self):
        """Test sparse helper is re-exported from shared module."""
        assert lexical_weights_to_sparse is shared_sparse

    def test_convert_lexical_weights_to_sparse_vector(self):
        """Test converting BGE-M3 lexical weights to Qdrant SparseVector."""
        # BGE-M3 returns dict with string keys
        lexical_weights = {"123": 0.5, "456": 0.8, "789": 0.3}

        sparse = lexical_weights_to_sparse(lexical_weights)

        assert isinstance(sparse, models.SparseVector)
        assert sparse.indices == [123, 456, 789]
        assert sparse.values == [0.5, 0.8, 0.3]

    def test_convert_empty_lexical_weights(self):
        """Test converting empty lexical weights."""
        sparse = lexical_weights_to_sparse({})

        assert isinstance(sparse, models.SparseVector)
        assert sparse.indices == []
        assert sparse.values == []
