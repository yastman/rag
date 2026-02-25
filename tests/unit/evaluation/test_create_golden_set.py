# tests/unit/evaluation/test_create_golden_set.py
"""Tests for src/evaluation/create_golden_set.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _run_and_capture() -> dict:
    """Run create_golden_test_set with a mocked open and return the written JSON."""
    import io

    from src.evaluation.create_golden_set import create_golden_test_set

    buf = io.StringIO()
    mock_file = MagicMock()
    mock_file.__enter__ = lambda _: buf
    mock_file.__exit__ = MagicMock(return_value=False)

    with patch("builtins.open", return_value=mock_file):
        with patch.object(Path, "mkdir"):
            create_golden_test_set()

    buf.seek(0)
    return json.loads(buf.read())


class TestCreateGoldenTestSet:
    """Tests for create_golden_test_set function."""

    def test_output_has_required_top_level_keys(self):
        """Test that output JSON has required top-level keys."""
        data = _run_and_capture()

        assert "version" in data
        assert "queries" in data
        assert "total_queries" in data
        assert "categories" in data
        assert "difficulty" in data

    def test_total_queries_matches_list_length(self):
        """Test that total_queries field matches actual query count."""
        data = _run_and_capture()

        assert data["total_queries"] == len(data["queries"])

    def test_categories_sum_equals_total(self):
        """Test that sum of category counts equals total queries."""
        data = _run_and_capture()

        category_sum = sum(data["categories"].values())
        assert category_sum == data["total_queries"]

    def test_each_query_has_required_fields(self):
        """Test that each query has id, query, expected_articles, category, difficulty."""
        data = _run_and_capture()

        required_fields = {"id", "query", "expected_articles", "category", "difficulty"}
        for query in data["queries"]:
            missing = required_fields - set(query.keys())
            assert not missing, f"Query {query.get('id')} missing fields: {missing}"

    def test_difficulty_levels_are_valid(self):
        """Test that all difficulty values are one of easy/medium/hard."""
        data = _run_and_capture()

        valid_difficulties = {"easy", "medium", "hard"}
        for query in data["queries"]:
            assert query["difficulty"] in valid_difficulties

    def test_expected_articles_are_lists_of_ints(self):
        """Test that expected_articles are non-empty lists of integers."""
        data = _run_and_capture()

        for query in data["queries"]:
            articles = query["expected_articles"]
            assert isinstance(articles, list)
            assert len(articles) >= 1
            for article in articles:
                assert isinstance(article, int)

    def test_query_ids_are_sequential(self):
        """Test that query IDs start at 1 and are sequential."""
        data = _run_and_capture()

        ids = [q["id"] for q in data["queries"]]
        assert ids == list(range(1, len(ids) + 1))
