"""Tests for validation query definitions."""

from pathlib import Path

import yaml

from scripts.validate_queries import (
    EDGE_CASE_QUERIES,
    GDRIVE_BGE_QUERIES,
    LEGAL_QUERIES,
    PROPERTY_QUERIES,
    ValidationQuery,
    get_cache_hit_queries,
    get_queries_for_collection,
    get_warmup_queries,
)


class TestValidationQueries:
    """Test query set definitions."""

    def test_property_queries_count(self):
        assert len(PROPERTY_QUERIES) == 14  # 6 simple + 8 complex

    def test_legal_queries_count(self):
        assert len(LEGAL_QUERIES) == 10  # 5 hard + 5 medium/easy

    def test_edge_case_queries_count(self):
        assert len(EDGE_CASE_QUERIES) == 3

    def test_gdrive_bge_queries_count(self):
        assert len(GDRIVE_BGE_QUERIES) == 30  # 10 easy + 10 medium + 10 hard

    def test_get_queries_for_legal(self):
        queries = get_queries_for_collection("legal_documents")
        # 10 legal + 3 edge cases
        assert len(queries) == 13
        assert all(isinstance(q, ValidationQuery) for q in queries)

    def test_get_queries_for_property(self):
        queries = get_queries_for_collection("contextual_bulgaria_voyage")
        # 14 property + 3 edge cases
        assert len(queries) == 17

    def test_get_queries_for_gdrive_bge(self):
        queries = get_queries_for_collection("gdrive_documents_bge")
        # 30 gdrive_bge + 3 edge cases
        assert len(queries) == 33
        assert all(isinstance(q, ValidationQuery) for q in queries)

    def test_get_queries_unknown_collection(self):
        queries = get_queries_for_collection("nonexistent")
        # Only edge cases
        assert len(queries) == 3

    def test_warmup_queries_subset(self):
        warmup = get_warmup_queries("legal_documents", count=3)
        assert len(warmup) == 3
        full = get_queries_for_collection("legal_documents")
        assert warmup == full[:3]

    def test_cache_hit_queries_mix(self):
        cold = get_queries_for_collection("legal_documents")
        cache = get_cache_hit_queries(cold, count=10)
        assert len(cache) <= 10
        # All cache queries should be from cold set
        for q in cache:
            assert q in cold

    def test_all_queries_have_required_fields(self):
        all_queries = PROPERTY_QUERIES + LEGAL_QUERIES + GDRIVE_BGE_QUERIES + EDGE_CASE_QUERIES
        for q in all_queries:
            assert q.text, f"Empty text: {q}"
            assert q.source in ("smoke", "eval", "manual"), f"Bad source: {q.source}"
            assert q.difficulty in ("easy", "medium", "hard"), f"Bad difficulty: {q.difficulty}"
            assert q.collection, f"Empty collection: {q}"

    def test_edge_case_rewrite_query_flagged(self):
        rewrite_queries = [q for q in EDGE_CASE_QUERIES if q.expect_rewrite]
        assert len(rewrite_queries) >= 1

    def test_legal_grounding_fixture_has_required_keys(self):
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "retrieval"
            / "legal_grounding_cases.yaml"
        )
        cases = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        assert all(
            {"query", "expected_topic", "expected_grounding_mode"} <= set(case) for case in cases
        )
