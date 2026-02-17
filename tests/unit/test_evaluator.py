"""Unit tests for src/evaluation/evaluator.py."""

import json
import tempfile

import numpy as np
import pytest

from src.evaluation.evaluator import SearchEvaluator


class TestSearchEvaluatorInit:
    """Test SearchEvaluator initialization."""

    def test_init_loads_ground_truth(self):
        """Test that init loads ground truth from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"queries": []}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)
            assert evaluator.ground_truth == {"queries": []}


class TestEvaluateQuery:
    """Test evaluate_query method."""

    def test_evaluate_query_recall_at_1_hit(self):
        """Test recall@1 when expected article is first."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            results = [
                {"article_number": "121", "score": 0.95},
                {"article_number": "122", "score": 0.85},
            ]

            metrics = evaluator.evaluate_query(query, results)

            assert metrics["recall@1"] == 1
            assert metrics["recall@3"] == 1
            assert metrics["recall@5"] == 1

    def test_evaluate_query_recall_at_1_miss(self):
        """Test recall@1 when expected article is not first."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            results = [
                {"article_number": "122", "score": 0.95},
                {"article_number": "121", "score": 0.85},
            ]

            metrics = evaluator.evaluate_query(query, results)

            assert metrics["recall@1"] == 0
            assert metrics["recall@3"] == 1

    def test_evaluate_query_mrr_first_position(self):
        """Test MRR when expected article is at position 1."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            results = [{"article_number": "121", "score": 0.95}]

            metrics = evaluator.evaluate_query(query, results)

            assert metrics["mrr"] == 1.0
            assert metrics["rank"] == 1

    def test_evaluate_query_mrr_second_position(self):
        """Test MRR when expected article is at position 2."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            results = [
                {"article_number": "122", "score": 0.95},
                {"article_number": "121", "score": 0.85},
            ]

            metrics = evaluator.evaluate_query(query, results)

            assert metrics["mrr"] == 0.5
            assert metrics["rank"] == 2

    def test_evaluate_query_mrr_not_found(self):
        """Test MRR when expected article is not in results."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            results = [{"article_number": "999", "score": 0.95}]

            metrics = evaluator.evaluate_query(query, results)

            assert metrics["mrr"] == 0.0
            assert metrics["rank"] is None

    def test_evaluate_query_ndcg_at_10(self):
        """Test NDCG@10 calculation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            # Expected at position 1 = perfect NDCG
            results = [{"article_number": "121", "score": 0.95}]

            metrics = evaluator.evaluate_query(query, results)

            assert metrics["ndcg@10"] == 1.0

    def test_evaluate_query_precision_at_k(self):
        """Test precision@K calculations."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            query = {"query": "test", "expected_article": "121"}
            results = [
                {"article_number": "121", "score": 0.95},
                {"article_number": "122", "score": 0.85},
                {"article_number": "123", "score": 0.80},
            ]

            metrics = evaluator.evaluate_query(query, results)

            # Only one relevant result at position 1
            assert metrics["precision@1"] == 1.0
            assert metrics["precision@3"] == pytest.approx(1 / 3)


class TestCalculateNDCG:
    """Test _calculate_ndcg method."""

    def test_ndcg_perfect_ranking(self):
        """Test NDCG with perfect ranking (expected at position 1)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            ndcg = evaluator._calculate_ndcg("121", ["121", "122", "123"])
            assert ndcg == 1.0

    def test_ndcg_expected_at_position_2(self):
        """Test NDCG with expected at position 2."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            ndcg = evaluator._calculate_ndcg("121", ["122", "121", "123"])
            # DCG = 1/log2(3) ≈ 0.63, IDCG = 1.0
            assert ndcg == pytest.approx(1 / np.log2(3))

    def test_ndcg_not_found(self):
        """Test NDCG when expected is not in results."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            ndcg = evaluator._calculate_ndcg("121", ["122", "123", "124"])
            assert ndcg == 0.0


class TestEvaluateQueries:
    """Test evaluate_queries method for batch evaluation."""

    def test_evaluate_queries_aggregation(self):
        """Test aggregated metrics from multiple queries."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            queries = [
                {"query": "query1", "expected_article": "121", "type": "semantic"},
                {"query": "query2", "expected_article": "122", "type": "exact"},
            ]

            search_results_map = {
                "query1": [{"article_number": "121", "score": 0.95}],
                "query2": [
                    {"article_number": "999", "score": 0.95},
                    {"article_number": "122", "score": 0.85},
                ],
            }

            result = evaluator.evaluate_queries(queries, search_results_map)

            assert result["total_queries"] == 2
            assert "metrics" in result
            # Average recall@1: (1 + 0) / 2 = 0.5
            assert result["metrics"]["recall@1"] == 0.5

    def test_evaluate_queries_by_type(self):
        """Test metrics broken down by query type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            queries = [
                {"query": "q1", "expected_article": "121", "type": "semantic"},
                {"query": "q2", "expected_article": "122", "type": "semantic"},
                {"query": "q3", "expected_article": "123", "type": "exact"},
            ]

            search_results_map = {
                "q1": [{"article_number": "121", "score": 0.95}],
                "q2": [{"article_number": "122", "score": 0.95}],
                "q3": [{"article_number": "123", "score": 0.95}],
            }

            result = evaluator.evaluate_queries(queries, search_results_map)

            assert "by_query_type" in result
            assert "semantic" in result["by_query_type"]
            assert result["by_query_type"]["semantic"]["count"] == 2

    def test_evaluate_queries_failure_rate(self):
        """Test failure rate calculation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            queries = [
                {"query": "q1", "expected_article": "121"},
                {"query": "q2", "expected_article": "122"},
            ]

            # q1 fails, q2 succeeds
            search_results_map = {
                "q1": [{"article_number": "999", "score": 0.95}],  # Wrong
                "q2": [{"article_number": "122", "score": 0.95}],  # Correct
            }

            result = evaluator.evaluate_queries(queries, search_results_map)

            # recall@10 = 0.5, failure_rate = 1 - 0.5 = 0.5
            assert result["metrics"]["failure_rate"] == 0.5


class TestCompareEngines:
    """Test compare_engines method."""

    @pytest.mark.filterwarnings("ignore:.*sample.*too small.*")
    def test_compare_engines_improvements(self):
        """Test improvement calculation between engines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            baseline_results = {
                "metrics": {
                    "recall@1": 0.80,
                    "recall@10": 0.90,
                    "mrr": 0.75,
                },
                "detailed_results": [],
            }

            hybrid_results = {
                "metrics": {
                    "recall@1": 0.90,  # +10%
                    "recall@10": 0.95,  # +5.5%
                    "mrr": 0.85,  # +13.3%
                },
                "detailed_results": [],
            }

            comparison = evaluator.compare_engines(baseline_results, hybrid_results)

            assert comparison["improvements"]["recall@1"]["absolute_diff"] == pytest.approx(0.10)
            assert comparison["improvements"]["recall@1"][
                "relative_improvement_pct"
            ] == pytest.approx(12.5)

    @pytest.mark.filterwarnings("ignore:.*sample.*too small.*")
    def test_compare_engines_failure_rate_improvement(self):
        """Test failure rate improvement (lower is better)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()

            evaluator = SearchEvaluator(f.name)

            baseline_results = {
                "metrics": {"failure_rate": 0.20},
                "detailed_results": [],
            }

            hybrid_results = {
                "metrics": {"failure_rate": 0.10},  # 50% reduction
                "detailed_results": [],
            }

            comparison = evaluator.compare_engines(baseline_results, hybrid_results)

            # For failure rate, improvement is (baseline - hybrid) / baseline
            assert comparison["improvements"]["failure_rate"]["relative_improvement_pct"] == 50.0
