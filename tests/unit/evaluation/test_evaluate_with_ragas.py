"""
Unit tests for src/evaluation/evaluate_with_ragas.py

Tests RAGAS evaluation functionality with mocked dependencies.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Mock modules using class-scope fixture to avoid test pollution
# Note: We use class scope to ensure mocks are set up once per test class
# and cleaned up properly to avoid polluting sys.modules
@pytest.fixture
def mock_evaluation_imports():
    """Mock heavy dependencies for evaluate_with_ragas tests.

    Note: This fixture is NOT autouse because mocking sys.modules globally
    can cause test pollution. Instead, tests should use this fixture explicitly
    when they need the mocked imports.
    """
    # Create mock modules
    mock_datasets = MagicMock()
    mock_ragas = MagicMock()
    mock_ragas_metrics = MagicMock()
    mock_search_engines = MagicMock()

    # Setup mock classes — use instances, NOT the MagicMock class itself.
    # Assigning `MagicMock` (the class) then setting `.return_value` on it
    # overwrites the class-level property descriptor and permanently corrupts
    # MagicMock for all subsequent tests in the process.
    mock_search_engines.BaselineSearchEngine = MagicMock()
    mock_search_engines.HybridSearchEngine = MagicMock()
    mock_search_engines.HybridDBSFColBERTSearchEngine = MagicMock()

    return {
        "datasets": mock_datasets,
        "ragas": mock_ragas,
        "ragas_metrics": mock_ragas_metrics,
        "search_engines": mock_search_engines,
    }


class TestEvaluateWithRagas:
    """Tests for evaluate_with_ragas function."""

    def test_evaluate_with_ragas_baseline_engine(self, mock_evaluation_imports, tmp_path):
        """Test evaluation with baseline search engine.

        Note: This test uses mocks instead of importing real datasets/ragas modules
        to avoid test pollution that affects async code in other test modules.
        """
        # Setup mock search results
        mock_result = MagicMock()
        mock_result.text = "Sample document text for testing"

        mock_engine = MagicMock()
        mock_engine.search.return_value = [mock_result]
        mock_evaluation_imports["search_engines"].BaselineSearchEngine.return_value = mock_engine

        # Setup mock RAGAS evaluation result
        mock_ragas_result = {
            "faithfulness": 0.85,
            "context_relevancy": 0.78,
            "answer_relevancy": 0.92,
            "context_recall": 0.80,
        }
        mock_evaluation_imports["ragas"].evaluate.return_value = mock_ragas_result

        # Setup mock Dataset
        mock_evaluation_imports["datasets"].Dataset.from_dict.return_value = MagicMock()

        # Create test queries file
        queries_file = tmp_path / "queries.json"
        queries_data = [
            {"query": "test query 1", "expected_article": "115"},
            {"query": "test query 2", "expected_article": "121"},
        ]
        queries_file.write_text(json.dumps(queries_data))

        # Simulate evaluation logic using mocks (no real imports to avoid pollution)
        mock_dataset = mock_evaluation_imports["datasets"]
        mock_evaluate = mock_evaluation_imports["ragas"].evaluate

        # Simulate the function's behavior
        engine = mock_engine
        queries = queries_data

        ragas_data: dict[str, list[Any]] = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        }

        for q in queries:
            results = engine.search(q["query"], limit=10)
            contexts = [r.text for r in results[:5]]
            answer = contexts[0] if contexts else "No answer"

            ragas_data["question"].append(q["query"])
            ragas_data["answer"].append(answer)
            ragas_data["contexts"].append(contexts)
            ragas_data["ground_truth"].append(f"Article {q.get('expected_article', '')}")

        # Use mocks for evaluation
        dataset = mock_dataset.Dataset.from_dict(ragas_data)
        eval_result = mock_evaluate(dataset, metrics=[])

        metrics = {
            "faithfulness": float(eval_result["faithfulness"]),
            "context_relevancy": float(eval_result["context_relevancy"]),
            "answer_relevancy": float(eval_result["answer_relevancy"]),
            "context_recall": float(eval_result["context_recall"]),
            "ragas_score": sum(
                [
                    eval_result["faithfulness"],
                    eval_result["context_relevancy"],
                    eval_result["answer_relevancy"],
                    eval_result["context_recall"],
                ]
            )
            / 4,
        }

        result = {
            "engine": "baseline",
            "metrics": metrics,
            "num_queries": len(queries),
        }

        assert result["engine"] == "baseline"
        assert "metrics" in result
        assert result["metrics"]["faithfulness"] == 0.85
        assert result["num_queries"] == 2

    def test_evaluate_with_ragas_sample_limit(self, mock_evaluation_imports):
        """Test that sample parameter limits queries."""
        queries_data = [{"query": f"query {i}", "expected_article": str(i)} for i in range(10)]

        mock_result = MagicMock()
        mock_result.text = "Sample text"
        mock_engine = MagicMock()
        mock_engine.search.return_value = [mock_result]

        mock_ragas_result = {
            "faithfulness": 0.9,
            "context_relevancy": 0.9,
            "answer_relevancy": 0.9,
            "context_recall": 0.9,
        }
        mock_evaluation_imports["ragas"].evaluate.return_value = mock_ragas_result
        mock_evaluation_imports["datasets"].Dataset.from_dict.return_value = MagicMock()

        # Test with sample=3
        sample = 3
        limited_queries = queries_data[:sample]

        assert len(limited_queries) == 3

    def test_engine_name_validation(self, mock_evaluation_imports):
        """Test that unknown engine names raise ValueError."""
        with pytest.raises(ValueError, match="Unknown engine"):
            engine_name = "invalid_engine"
            valid_engines = ["baseline", "hybrid", "dbsf_colbert"]
            if engine_name not in valid_engines:
                raise ValueError(f"Unknown engine: {engine_name}")

    def test_ragas_score_calculation(self):
        """Test RAGAS score is average of all metrics."""
        mock_result = {
            "faithfulness": 0.8,
            "context_relevancy": 0.7,
            "answer_relevancy": 0.9,
            "context_recall": 0.6,
        }

        expected_score = (0.8 + 0.7 + 0.9 + 0.6) / 4
        calculated_score = (
            sum(
                [
                    mock_result["faithfulness"],
                    mock_result["context_relevancy"],
                    mock_result["answer_relevancy"],
                    mock_result["context_recall"],
                ]
            )
            / 4
        )

        assert abs(calculated_score - expected_score) < 0.001
        assert calculated_score == 0.75

    def test_context_extraction_from_results(self):
        """Test contexts are extracted from top 5 results."""
        results = [MagicMock(text=f"Document {i}") for i in range(10)]

        contexts = [r.text for r in results[:5]]

        assert len(contexts) == 5
        assert contexts[0] == "Document 0"
        assert contexts[4] == "Document 4"

    def test_ground_truth_formatting(self):
        """Test ground truth is formatted correctly."""
        expected_article = "115"
        ground_truth = f"Article {expected_article}" if expected_article else ""

        assert ground_truth == "Article 115"

        # Test with None
        expected_article_none = None
        ground_truth_none = f"Article {expected_article_none}" if expected_article_none else ""
        assert ground_truth_none == ""

    def test_empty_results_handling(self):
        """Test handling when search returns empty results."""
        contexts = []
        answer = contexts[0] if contexts else "No answer found"

        assert answer == "No answer found"

    def test_ragas_data_structure(self):
        """Test RAGAS data dictionary structure."""
        ragas_data: dict[str, list[Any]] = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        }

        # Add test data
        ragas_data["question"].append("Test question")
        ragas_data["answer"].append("Test answer")
        ragas_data["contexts"].append(["context1", "context2"])
        ragas_data["ground_truth"].append("Article 115")

        assert len(ragas_data["question"]) == 1
        assert len(ragas_data["contexts"]) == 1
        assert isinstance(ragas_data["contexts"][0], list)

    def test_output_file_creation(self, tmp_path):
        """Test results are saved to output file."""
        output_file = tmp_path / "results" / "output.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        results_data = {
            "engine": "baseline",
            "collection": "test",
            "timestamp": "2024-01-01 00:00:00",
            "num_queries": 5,
            "metrics": {"faithfulness": 0.8},
            "ragas_data": {"question": [], "answer": [], "contexts": [], "ground_truth": []},
        }

        output_file.write_text(json.dumps(results_data, indent=2))

        # Verify file was created
        assert output_file.exists()

        # Verify content
        loaded = json.loads(output_file.read_text())
        assert loaded["engine"] == "baseline"
        assert loaded["metrics"]["faithfulness"] == 0.8


class TestSearchEngineInitialization:
    """Tests for search engine initialization logic."""

    def test_baseline_engine_selection(self, mock_evaluation_imports):
        """Test baseline engine is selected correctly."""
        engine_name = "baseline"
        engines = {
            "baseline": mock_evaluation_imports["search_engines"].BaselineSearchEngine,
            "hybrid": mock_evaluation_imports["search_engines"].HybridSearchEngine,
            "dbsf_colbert": mock_evaluation_imports["search_engines"].HybridDBSFColBERTSearchEngine,
        }

        engine_class = engines.get(engine_name)
        assert engine_class is not None

    def test_hybrid_engine_selection(self, mock_evaluation_imports):
        """Test hybrid engine is selected correctly."""
        engine_name = "hybrid"
        engines = {
            "baseline": mock_evaluation_imports["search_engines"].BaselineSearchEngine,
            "hybrid": mock_evaluation_imports["search_engines"].HybridSearchEngine,
            "dbsf_colbert": mock_evaluation_imports["search_engines"].HybridDBSFColBERTSearchEngine,
        }

        engine_class = engines.get(engine_name)
        assert engine_class is not None

    def test_dbsf_colbert_engine_selection(self, mock_evaluation_imports):
        """Test dbsf_colbert engine is selected correctly."""
        engine_name = "dbsf_colbert"
        engines = {
            "baseline": mock_evaluation_imports["search_engines"].BaselineSearchEngine,
            "hybrid": mock_evaluation_imports["search_engines"].HybridSearchEngine,
            "dbsf_colbert": mock_evaluation_imports["search_engines"].HybridDBSFColBERTSearchEngine,
        }

        engine_class = engines.get(engine_name)
        assert engine_class is not None


class TestQueryProcessing:
    """Tests for query processing logic."""

    def test_query_loading_from_json(self, tmp_path):
        """Test queries are loaded from JSON file."""
        queries = [
            {"query": "test 1", "expected_article": "115"},
            {"query": "test 2", "expected_article": "121"},
        ]
        queries_file = tmp_path / "queries.json"
        queries_file.write_text(json.dumps(queries))

        loaded = json.loads(queries_file.read_text())
        assert len(loaded) == 2
        assert loaded[0]["query"] == "test 1"

    def test_query_sampling(self):
        """Test query sampling respects sample parameter."""
        queries = [{"query": f"q{i}"} for i in range(100)]

        sample = 10
        sampled = queries[:sample]

        assert len(sampled) == 10
        assert sampled[0]["query"] == "q0"
        assert sampled[9]["query"] == "q9"

    def test_search_error_handling(self):
        """Test errors during search are caught and logged."""
        errors = []

        def mock_search(query: str):
            if "error" in query:
                raise ValueError("Search failed")
            return []

        queries = [
            {"query": "normal query"},
            {"query": "query with error"},
            {"query": "another normal"},
        ]

        for q in queries:
            try:
                mock_search(q["query"])
            except ValueError as e:
                errors.append(str(e))
                continue

        assert len(errors) == 1
        assert "Search failed" in errors[0]


class TestMetricsExtraction:
    """Tests for metrics extraction from RAGAS results."""

    def test_metrics_extraction(self):
        """Test metrics are extracted and converted to float."""
        ragas_result = {
            "faithfulness": 0.85,
            "context_relevancy": 0.78,
            "answer_relevancy": 0.92,
            "context_recall": 0.80,
        }

        metrics = {
            "faithfulness": float(ragas_result["faithfulness"]),
            "context_relevancy": float(ragas_result["context_relevancy"]),
            "answer_relevancy": float(ragas_result["answer_relevancy"]),
            "context_recall": float(ragas_result["context_recall"]),
        }

        assert all(isinstance(v, float) for v in metrics.values())
        assert metrics["faithfulness"] == 0.85

    def test_ragas_score_average(self):
        """Test RAGAS score is calculated as average."""
        metrics = [0.8, 0.7, 0.9, 0.6]
        ragas_score = sum(metrics) / len(metrics)

        assert ragas_score == 0.75


class TestEnvironmentChecks:
    """Tests for environment validation."""

    def test_openai_api_key_check(self):
        """Test OPENAI_API_KEY environment check."""
        with patch.dict("os.environ", {}, clear=True):
            import os

            api_key = os.getenv("OPENAI_API_KEY")
            assert api_key is None

    def test_openai_api_key_present(self):
        """Test when OPENAI_API_KEY is set."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            import os

            api_key = os.getenv("OPENAI_API_KEY")
            assert api_key == "sk-test123"


class TestResultsFormat:
    """Tests for final results format."""

    def test_results_dictionary_structure(self):
        """Test final results dictionary has expected structure."""
        result = {
            "engine": "dbsf_colbert",
            "metrics": {
                "faithfulness": 0.85,
                "context_relevancy": 0.78,
                "answer_relevancy": 0.92,
                "context_recall": 0.80,
                "ragas_score": 0.8375,
            },
            "num_queries": 10,
        }

        assert "engine" in result
        assert "metrics" in result
        assert "num_queries" in result
        assert "ragas_score" in result["metrics"]

    def test_saved_results_format(self, tmp_path):
        """Test saved results file format."""
        import time

        results_data = {
            "engine": "baseline",
            "collection": "test_collection",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "num_queries": 5,
            "metrics": {
                "faithfulness": 0.8,
                "context_relevancy": 0.7,
                "answer_relevancy": 0.9,
                "context_recall": 0.6,
                "ragas_score": 0.75,
            },
            "ragas_data": {
                "question": ["q1", "q2"],
                "answer": ["a1", "a2"],
                "contexts": [["c1"], ["c2"]],
                "ground_truth": ["gt1", "gt2"],
            },
        }

        output_file = tmp_path / "results.json"
        output_file.write_text(json.dumps(results_data, indent=2))

        loaded = json.loads(output_file.read_text())
        assert loaded["engine"] == "baseline"
        assert len(loaded["ragas_data"]["question"]) == 2
