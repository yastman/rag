# tests/unit/evaluation/test_search_engines_eval.py
"""Tests for src/evaluation/search_engines.py (evaluation module)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


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

    @patch("src.evaluation.search_engines.Settings")
    def test_search_engine_init(self, mock_settings_cls):
        """Test SearchEngine initialization."""
        from src.evaluation.search_engines import SearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        # SearchEngine is abstract, so we test via concrete implementation
        # Just verify the import works
        assert SearchEngine is not None

    @patch("src.evaluation.search_engines.Settings")
    def test_extract_article_number(self, mock_settings_cls):
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

    @patch("src.evaluation.search_engines.Settings")
    def test_extract_article_number_missing(self, mock_settings_cls):
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

    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_init(self, mock_settings_cls):
        """Test BaselineSearchEngine initialization."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = BaselineSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"
        assert engine.embedding_model == mock_model

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_search_generates_embedding(self, mock_settings_cls, mock_requests):
        """Test that search generates dense embedding."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {"dense_vecs": np.array([0.1, 0.2, 0.3])}

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        engine = BaselineSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        mock_model.encode.assert_called_once_with(
            "test query",
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_baseline_search_returns_results(self, mock_settings_cls, mock_requests):
        """Test that search returns formatted results."""
        from src.evaluation.search_engines import BaselineSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        mock_model.encode.return_value = {"dense_vecs": np.array([0.1, 0.2, 0.3])}

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [
                {
                    "id": 1,
                    "score": 0.95,
                    "payload": {
                        "article_number": "115",
                        "text": "Sample article text for testing",
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        engine = BaselineSearchEngine("test_collection", mock_model)
        results = engine.search("test query", top_k=5)

        assert len(results) == 1
        assert results[0]["article_number"] == "115"
        assert results[0]["score"] == 0.95


class TestHybridSearchEngine:
    """Tests for HybridSearchEngine."""

    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_init(self, mock_settings_cls):
        """Test HybridSearchEngine initialization."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = HybridSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"
        assert engine.embedding_model == mock_model

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_generates_all_embeddings(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        mock_model.encode.assert_called_once_with(
            "test query",
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_converts_sparse_indices(self, mock_settings_cls, mock_requests):
        """Test that hybrid search converts sparse indices to ints."""
        from src.evaluation.search_engines import HybridSearchEngine

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        # Dict format with string keys (as BGE-M3 returns)
        mock_model.encode.return_value = {
            "dense_vecs": np.array([0.1, 0.2]),
            "lexical_weights": {"100": 0.5, "200": 0.8},
            "colbert_vecs": np.array([[0.1, 0.2]]),
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Verify the request was made with correct payload
        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        # Check that sparse indices are integers
        prefetch = payload["prefetch"][1]  # Second prefetch is sparse
        sparse_query = prefetch["query"]
        assert all(isinstance(idx, int) for idx in sparse_query["indices"])

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_handles_scipy_sparse(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Should not raise exception
        mock_requests.post.assert_called_once()

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_hybrid_search_uses_rrf_fusion(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Verify RRF fusion is used
        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]
        assert payload["query"]["fusion"] == "rrf"


class TestHybridDBSFColBERTSearchEngine:
    """Tests for HybridDBSFColBERTSearchEngine."""

    @patch("src.evaluation.search_engines.Settings")
    def test_dbsf_colbert_init(self, mock_settings_cls):
        """Test HybridDBSFColBERTSearchEngine initialization."""
        from src.evaluation.search_engines import HybridDBSFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = HybridDBSFColBERTSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_dbsf_colbert_uses_dbsf_fusion(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridDBSFColBERTSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        # Verify DBSF fusion is used in inner prefetch
        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        # Check nested prefetch structure
        outer_prefetch = payload["prefetch"][0]
        assert outer_prefetch["query"]["fusion"] == "dbsf"

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_dbsf_colbert_uses_colbert_for_rerank(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridDBSFColBERTSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        # Final query uses ColBERT
        assert payload["using"] == "colbert"


class TestHybridRRFColBERTSearchEngine:
    """Tests for HybridRRFColBERTSearchEngine."""

    @patch("src.evaluation.search_engines.Settings")
    def test_rrf_colbert_init(self, mock_settings_cls):
        """Test HybridRRFColBERTSearchEngine initialization."""
        from src.evaluation.search_engines import HybridRRFColBERTSearchEngine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()
        engine = HybridRRFColBERTSearchEngine("test_collection", mock_model)

        assert engine.collection_name == "test_collection"

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_rrf_colbert_uses_rrf_fusion(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"points": []}}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridRRFColBERTSearchEngine("test_collection", mock_model)
        engine.search("test query", top_k=5)

        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        # Check nested prefetch structure uses RRF
        outer_prefetch = payload["prefetch"][0]
        assert outer_prefetch["query"]["fusion"] == "rrf"


class TestCreateSearchEngine:
    """Tests for create_search_engine factory function."""

    @patch("src.evaluation.search_engines.Settings")
    def test_create_baseline_engine(self, mock_settings_cls):
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

    @patch("src.evaluation.search_engines.Settings")
    def test_create_hybrid_engine(self, mock_settings_cls):
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

    @patch("src.evaluation.search_engines.Settings")
    def test_create_dbsf_colbert_engine(self, mock_settings_cls):
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

    @patch("src.evaluation.search_engines.Settings")
    def test_create_rrf_colbert_engine(self, mock_settings_cls):
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

    @patch("src.evaluation.search_engines.Settings")
    def test_create_unknown_engine_raises_error(self, mock_settings_cls):
        """Test that unknown engine type raises ValueError."""
        from src.evaluation.search_engines import create_search_engine

        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        mock_model = MagicMock()

        with pytest.raises(ValueError, match="Unknown engine type"):
            create_search_engine("unknown_engine", "test_collection", mock_model)


class TestSearchEngineResponseParsing:
    """Tests for response parsing in search engines."""

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_parse_dict_result_format(self, mock_settings_cls, mock_requests):
        """Test parsing response with dict result format."""
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

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "points": [
                    {
                        "id": 1,
                        "score": 0.95,
                        "payload": {"article_number": "115", "text": "Test text"},
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        results = engine.search("test", top_k=5)

        assert len(results) == 1
        assert results[0]["article_number"] == "115"

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_parse_list_result_format(self, mock_settings_cls, mock_requests):
        """Test parsing response with list result format."""
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

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": [
                {
                    "id": 1,
                    "score": 0.95,
                    "payload": {"article_number": "115", "text": "Test text"},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        results = engine.search("test", top_k=5)

        assert len(results) == 1
        assert results[0]["article_number"] == "115"

    @patch("src.evaluation.search_engines.requests")
    @patch("src.evaluation.search_engines.Settings")
    def test_parse_empty_result(self, mock_settings_cls, mock_requests):
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

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": None}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response

        engine = HybridSearchEngine("test_collection", mock_model)
        results = engine.search("test", top_k=5)

        assert len(results) == 0
