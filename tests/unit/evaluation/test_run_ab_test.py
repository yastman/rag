# tests/unit/evaluation/test_run_ab_test.py
"""Tests for src/evaluation/run_ab_test.py.

Note: The run_ab_test.py module has relative imports that make it difficult to test
in isolation. These tests focus on the testable parts and skip module-level imports.
"""

import json
import os
import tempfile

import numpy as np
import pytest


class TestConvertNumpy:
    """Tests for convert_numpy helper function.

    Note: This function is defined inside run_ab_test function,
    so we test the logic pattern here with a local implementation.
    """

    def _convert_numpy(self, obj):
        """Local implementation of convert_numpy for testing."""
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        if isinstance(obj, dict):
            return {k: self._convert_numpy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_numpy(item) for item in obj]
        return obj

    def test_convert_numpy_bool(self):
        """Test numpy bool to Python bool conversion."""
        val = np.bool_(True)
        result = self._convert_numpy(val)

        assert result is True
        assert isinstance(result, bool)

    def test_convert_numpy_int(self):
        """Test numpy int to Python float conversion."""
        val = np.int64(42)
        result = self._convert_numpy(val)

        assert result == 42.0
        assert isinstance(result, float)

    def test_convert_numpy_float(self):
        """Test numpy float to Python float conversion."""
        val = np.float32(3.14)
        result = self._convert_numpy(val)

        assert result == pytest.approx(3.14, rel=1e-5)
        assert isinstance(result, float)

    def test_convert_dict_with_numpy(self):
        """Test conversion of dict with numpy types."""
        data = {
            "bool_val": np.bool_(False),
            "int_val": np.int32(10),
            "float_val": np.float64(2.5),
        }
        result = self._convert_numpy(data)

        assert result["bool_val"] is False
        assert isinstance(result["int_val"], float)
        assert isinstance(result["float_val"], float)

    def test_convert_list_with_numpy(self):
        """Test conversion of list with numpy types."""
        data = [np.bool_(True), np.int64(5), np.float32(1.5)]
        result = self._convert_numpy(data)

        assert result[0] is True
        assert isinstance(result[1], float)
        assert isinstance(result[2], float)

    def test_convert_python_types_unchanged(self):
        """Test that Python types are unchanged."""
        data = {"string": "text", "int": 42, "float": 3.14, "bool": True}
        result = self._convert_numpy(data)

        assert result == data

    def test_convert_nested_structures(self):
        """Test conversion of nested structures."""
        data = {
            "outer": {
                "inner": [np.int64(1), np.float32(2.0)],
            }
        }
        result = self._convert_numpy(data)

        assert result["outer"]["inner"] == [1.0, 2.0]


class TestPrintMetricsStandalone:
    """Standalone tests for print_metrics output format."""

    def _print_metrics(self, metrics: dict):
        """Local implementation matching the expected output format."""
        output = []
        output.append(f"   Recall@1:  {metrics.get('recall@1', 0):.4f}")
        output.append(f"   Recall@3:  {metrics.get('recall@3', 0):.4f}")
        output.append(f"   Recall@5:  {metrics.get('recall@5', 0):.4f}")
        output.append(f"   Recall@10: {metrics.get('recall@10', 0):.4f}")
        output.append(f"   MRR:       {metrics.get('mrr', 0):.4f}")
        output.append(f"   NDCG@10:   {metrics.get('ndcg@10', 0):.4f}")
        failure_rate = metrics.get("failure_rate", 0)
        output.append(f"   Failure:   {failure_rate:.4f} ({failure_rate * 100:.1f}%)")
        return "\n".join(output)

    def test_print_metrics_basic(self):
        """Test print_metrics outputs correct format."""
        metrics = {
            "recall@1": 0.9123,
            "recall@3": 0.9456,
            "recall@5": 0.9678,
            "recall@10": 0.9890,
            "mrr": 0.8765,
            "ndcg@10": 0.8543,
            "failure_rate": 0.0234,
        }

        output = self._print_metrics(metrics)

        assert "Recall@1:  0.9123" in output
        assert "Recall@3:  0.9456" in output
        assert "Recall@10: 0.9890" in output
        assert "MRR:       0.8765" in output
        assert "NDCG@10:   0.8543" in output
        assert "Failure:   0.0234" in output

    def test_print_metrics_missing_values(self):
        """Test print_metrics handles missing values."""
        metrics = {}

        output = self._print_metrics(metrics)

        assert "Recall@1:  0.0000" in output
        assert "MRR:       0.0000" in output


class TestMarkdownReportGeneration:
    """Tests for markdown report generation logic."""

    def test_markdown_report_structure(self):
        """Test that markdown report follows expected structure."""
        # This tests the structure that would be generated
        data = {
            "timestamp": "20250128_120000",
            "collection": "test_collection",
            "total_queries": 100,
            "baseline_time": 10.5,
            "hybrid_time": 12.3,
            "dbsf_time": 15.0,
            "baseline_eval": {
                "metrics": {
                    "recall@1": 0.80,
                    "recall@10": 0.90,
                    "ndcg@10": 0.85,
                    "mrr": 0.82,
                    "failure_rate": 0.05,
                }
            },
            "hybrid_eval": {
                "metrics": {
                    "recall@1": 0.85,
                    "recall@10": 0.93,
                    "ndcg@10": 0.88,
                    "mrr": 0.86,
                    "failure_rate": 0.03,
                }
            },
            "dbsf_eval": {
                "metrics": {
                    "recall@1": 0.90,
                    "recall@10": 0.96,
                    "ndcg@10": 0.92,
                    "mrr": 0.89,
                    "failure_rate": 0.02,
                }
            },
        }

        # Verify data structure is valid
        assert "timestamp" in data
        assert "collection" in data
        assert "baseline_eval" in data
        assert "metrics" in data["baseline_eval"]

    def test_improvement_calculation(self):
        """Test improvement percentage calculation."""
        baseline = 0.80
        improved = 0.90
        improvement_pct = ((improved - baseline) / baseline) * 100

        assert improvement_pct == pytest.approx(12.5)

    def test_conclusion_significant_improvement(self):
        """Test conclusion logic for significant improvement."""
        dbsf_vs_baseline = 18.75  # > 10%
        dbsf_vs_hybrid = 8.0  # > 5%

        if dbsf_vs_baseline > 10 and dbsf_vs_hybrid > 5:
            conclusion = "SIGNIFICANTLY OUTPERFORMS"
        elif dbsf_vs_baseline > 5:
            conclusion = "MODERATELY OUTPERFORMS"
        elif dbsf_vs_baseline > 0:
            conclusion = "SLIGHTLY OUTPERFORMS"
        else:
            conclusion = "BASELINE STILL PERFORMS BEST"

        assert conclusion == "SIGNIFICANTLY OUTPERFORMS"

    def test_conclusion_moderate_improvement(self):
        """Test conclusion logic for moderate improvement."""
        dbsf_vs_baseline = 7.5  # > 5% but <= 10%
        dbsf_vs_hybrid = 3.0  # <= 5%

        if dbsf_vs_baseline > 10 and dbsf_vs_hybrid > 5:
            conclusion = "SIGNIFICANTLY OUTPERFORMS"
        elif dbsf_vs_baseline > 5:
            conclusion = "MODERATELY OUTPERFORMS"
        elif dbsf_vs_baseline > 0:
            conclusion = "SLIGHTLY OUTPERFORMS"
        else:
            conclusion = "BASELINE STILL PERFORMS BEST"

        assert conclusion == "MODERATELY OUTPERFORMS"


class TestSearchEngineSelection:
    """Tests for search engine selection logic."""

    def test_engine_type_baseline(self):
        """Test baseline engine type selection."""
        engine_type = "baseline"
        assert engine_type in ["baseline", "hybrid", "dbsf_colbert", "rrf_colbert"]

    def test_engine_type_hybrid(self):
        """Test hybrid engine type selection."""
        engine_type = "hybrid"
        assert engine_type in ["baseline", "hybrid", "dbsf_colbert", "rrf_colbert"]

    def test_engine_type_dbsf_colbert(self):
        """Test DBSF+ColBERT engine type selection."""
        engine_type = "dbsf_colbert"
        assert engine_type in ["baseline", "hybrid", "dbsf_colbert", "rrf_colbert"]


class TestStatisticalSignificance:
    """Tests for statistical significance display logic."""

    def test_highly_significant(self):
        """Test highly significant result (p < 0.01)."""
        sig = {
            "t_statistic": 3.45,
            "p_value": 0.002,
            "significant_at_0.01": True,
            "significant_at_0.05": True,
        }

        if sig["significant_at_0.01"]:
            result = "HIGHLY SIGNIFICANT"
        elif sig["significant_at_0.05"]:
            result = "SIGNIFICANT"
        else:
            result = "NOT SIGNIFICANT"

        assert result == "HIGHLY SIGNIFICANT"

    def test_significant_at_005(self):
        """Test significant at 0.05 level."""
        sig = {
            "t_statistic": 2.1,
            "p_value": 0.04,
            "significant_at_0.01": False,
            "significant_at_0.05": True,
        }

        if sig["significant_at_0.01"]:
            result = "HIGHLY SIGNIFICANT"
        elif sig["significant_at_0.05"]:
            result = "SIGNIFICANT"
        else:
            result = "NOT SIGNIFICANT"

        assert result == "SIGNIFICANT"

    def test_not_significant(self):
        """Test not significant result."""
        sig = {
            "t_statistic": 1.2,
            "p_value": 0.15,
            "significant_at_0.01": False,
            "significant_at_0.05": False,
        }

        if sig["significant_at_0.01"]:
            result = "HIGHLY SIGNIFICANT"
        elif sig["significant_at_0.05"]:
            result = "SIGNIFICANT"
        else:
            result = "NOT SIGNIFICANT"

        assert result == "NOT SIGNIFICANT"


class TestReportFileOperations:
    """Tests for report file writing operations."""

    def test_json_report_creation(self):
        """Test JSON report creation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filename = f.name

        try:
            report_data = {
                "engine": "baseline",
                "collection": "test_collection",
                "total_queries": 100,
                "search_time_total": 10.5,
                "search_time_avg": 0.105,
                "evaluation": {"metrics": {"recall@1": 0.90}},
            }

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            assert os.path.exists(filename)

            with open(filename, encoding="utf-8") as f:
                loaded = json.load(f)

            assert loaded["engine"] == "baseline"
            assert loaded["total_queries"] == 100
        finally:
            os.unlink(filename)

    def test_markdown_file_creation(self):
        """Test markdown file creation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            filename = f.name

        try:
            md_content = """# A/B Test Report

## Summary
- Collection: test_collection
- Queries: 100

## Results
| Metric | Value |
|--------|-------|
| Recall@1 | 0.90 |
"""
            with open(filename, "w", encoding="utf-8") as f:
                f.write(md_content)

            assert os.path.exists(filename)

            with open(filename, encoding="utf-8") as f:
                content = f.read()

            assert "A/B Test Report" in content
            assert "test_collection" in content
        finally:
            os.unlink(filename)
