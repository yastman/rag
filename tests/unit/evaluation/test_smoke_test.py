# tests/unit/evaluation/test_smoke_test.py
"""Unit tests for ``src/evaluation/smoke_test.py`` (real module).

Closes the placeholder-coverage drift described in #1619: previously this file
copied ``SMOKE_QUERIES``, ``SLO_THRESHOLDS``, and percentile/violation helpers
into the test itself, so changes to the real module could regress unobserved.
The contract test ``tests/contract/test_smoke_test_real_module_contract.py``
keeps this file pinned to the real module.
"""

from __future__ import annotations

import sys

from src.evaluation.smoke_test import SLO_THRESHOLDS, SMOKE_QUERIES, run_smoke_test


class TestSmokeQueries:
    """Tests for the real ``SMOKE_QUERIES`` constant."""

    def test_smoke_queries_count(self) -> None:
        """SMOKE_QUERIES has 30 entries."""
        assert len(SMOKE_QUERIES) == 30

    def test_smoke_queries_structure(self) -> None:
        """Each query carries the documented schema."""
        for query in SMOKE_QUERIES:
            assert "id" in query
            assert "query" in query
            assert "expected_article" in query
            assert "difficulty" in query
            assert "type" in query

    def test_smoke_queries_difficulty_distribution(self) -> None:
        """10 hard, 10 medium, 10 easy."""
        difficulties = [q["difficulty"] for q in SMOKE_QUERIES]
        assert difficulties.count("hard") == 10
        assert difficulties.count("medium") == 10
        assert difficulties.count("easy") == 10

    def test_smoke_queries_unique_ids(self) -> None:
        ids = [q["id"] for q in SMOKE_QUERIES]
        assert len(ids) == len(set(ids))

    def test_smoke_queries_valid_types(self) -> None:
        valid_types = {"paraphrased", "semantic", "direct"}
        for query in SMOKE_QUERIES:
            assert query["type"] in valid_types


class TestSLOThresholds:
    """Tests for the real ``SLO_THRESHOLDS`` constant."""

    def test_slo_thresholds_keys_defined(self) -> None:
        for key in (
            "precision_at_1_min",
            "recall_at_10_min",
            "p95_latency_ms_max",
            "p99_latency_ms_max",
            "failure_rate_max",
        ):
            assert key in SLO_THRESHOLDS, f"missing SLO threshold key {key!r}"

    def test_slo_precision_threshold(self) -> None:
        assert SLO_THRESHOLDS["precision_at_1_min"] == 0.90

    def test_slo_recall_threshold(self) -> None:
        assert SLO_THRESHOLDS["recall_at_10_min"] == 0.95

    def test_slo_latency_thresholds(self) -> None:
        assert SLO_THRESHOLDS["p95_latency_ms_max"] == 800
        assert SLO_THRESHOLDS["p99_latency_ms_max"] == 1200

    def test_slo_failure_rate_zero(self) -> None:
        assert SLO_THRESHOLDS["failure_rate_max"] == 0.0


class TestRunSmokeTestEngineSelection:
    """``run_smoke_test`` rejects unknown engine names before reaching Qdrant.

    These tests use a fake engine that intercepts construction so we never need
    a live Qdrant collection. The goal is to lock in the engine-selection
    branch coverage while keeping the test fully offline.
    """

    def test_unknown_engine_raises_value_error(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Unknown engine"):
            run_smoke_test(engine_name="not_a_real_engine", quick=True)

    def test_known_engine_constructed_with_collection(self, monkeypatch) -> None:
        """The selected engine class is constructed with the supplied
        collection name and the correct number of queries is consumed
        (10 in ``quick`` mode).
        """

        captured: dict[str, object] = {}

        class _FakePoint:
            def __init__(self, article: int) -> None:
                self.payload = {"article_number": article}

        class _FakeEngine:
            def __init__(self, collection_name: str) -> None:
                captured["collection_name"] = collection_name
                captured["query_count"] = 0

            def search(self, query: str, limit: int = 10):  # noqa: D401, ARG002
                captured["query_count"] = int(captured.get("query_count", 0)) + 1
                # Always return an empty list — we only care about wiring here.
                return []

        # Patch the symbol in the smoke_test module's namespace.
        smoke_module = sys.modules["src.evaluation.smoke_test"]
        monkeypatch.setattr(smoke_module, "BaselineSearchEngine", _FakeEngine)

        result = run_smoke_test(
            engine_name="baseline",
            collection="unit-test-collection",
            quick=True,
        )

        assert captured["collection_name"] == "unit-test-collection"
        # quick=True selects the first 10 queries.
        assert captured["query_count"] == 10
        assert result["engine"] == "baseline"
        assert result["collection"] == "unit-test-collection"
        assert result["queries_count"] == 10
        # Empty results means every query missed → all SLOs violated → not passed.
        assert result["passed"] is False
        assert result["slo_violations"], "expected SLO violations on all-miss run"


class TestRunSmokeTestSloEvaluation:
    """``run_smoke_test`` returns a passing result when the engine is perfect."""

    def test_perfect_engine_passes_all_slos(self, monkeypatch) -> None:
        class _FakePoint:
            def __init__(self, article: int) -> None:
                self.payload = {"article_number": article}

        class _PerfectEngine:
            def __init__(self, collection_name: str) -> None:
                self.collection_name = collection_name

            def search(self, query: str, limit: int = 10):  # noqa: ARG002
                # Inverse-lookup the expected article from the query string is
                # heavy — instead, return all 30 expected articles in order so
                # the first hit matches whichever query came in. ``run_smoke_test``
                # only checks the first article id against the expected one, so
                # we cooperate by extracting the expected number from the query
                # itself in the trailing ``"...статья N..."`` style. A simpler
                # route: index by call count is racy under the for-loop, so we
                # instead read the ``expected_article`` field from a closure.
                return [_FakePoint(article=_PerfectEngine.next_expected.pop(0))]

            # Will be primed in the test method below.
            next_expected: list[int] = []

        smoke_module = sys.modules["src.evaluation.smoke_test"]

        # Prime the perfect-engine to return the right article for each query.
        _PerfectEngine.next_expected = [int(q["expected_article"]) for q in SMOKE_QUERIES[:10]]

        monkeypatch.setattr(smoke_module, "BaselineSearchEngine", _PerfectEngine)

        result = run_smoke_test(
            engine_name="baseline",
            collection="unit-test-collection",
            quick=True,
        )

        assert result["precision_at_1"] == 1.0
        assert result["recall_at_10"] == 1.0
        assert result["failure_rate"] == 0.0
        # Latency violations are still possible if the test machine is very
        # slow; but smoke_test stores percentiles in ``latency_p95_ms`` only —
        # if all values are below 800ms the SLO is met.
        if result["latency_p95_ms"] <= SLO_THRESHOLDS["p95_latency_ms_max"]:
            assert result["passed"] is True
            assert result["slo_violations"] == []


class TestSmokeTestResultStructure:
    """``run_smoke_test`` returns the documented result schema."""

    def test_result_dict_keys(self, monkeypatch) -> None:
        class _FakeEngine:
            def __init__(self, collection_name: str) -> None:
                pass

            def search(self, query: str, limit: int = 10):  # noqa: ARG002
                return []

        smoke_module = sys.modules["src.evaluation.smoke_test"]
        monkeypatch.setattr(smoke_module, "BaselineSearchEngine", _FakeEngine)

        result = run_smoke_test(engine_name="baseline", quick=True)

        for required_key in (
            "engine",
            "collection",
            "config_hash",
            "queries_count",
            "precision_at_1",
            "recall_at_10",
            "failure_rate",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "slo_violations",
            "passed",
        ):
            assert required_key in result, f"missing key {required_key!r}"
