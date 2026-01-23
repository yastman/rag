# tests/smoke/test_smoke_routing.py
"""Smoke tests for query routing."""

from telegram_bot.services.query_router import (
    QueryType,
    classify_query,
    get_chitchat_response,
)
from tests.smoke.queries import SMOKE_QUERIES, ExpectedQueryType, get_queries_by_type


class TestSmokeRouting:
    """Test query routing for all 20 smoke queries."""

    def test_distribution_is_6_6_8(self):
        """Verify 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX."""
        assert len(get_queries_by_type(ExpectedQueryType.CHITCHAT)) == 6
        assert len(get_queries_by_type(ExpectedQueryType.SIMPLE)) == 6
        assert len(get_queries_by_type(ExpectedQueryType.COMPLEX)) == 8
        assert len(SMOKE_QUERIES) == 20

    def test_chitchat_queries_classified_correctly(self):
        """All CHITCHAT queries should be classified as CHITCHAT."""
        for query in get_queries_by_type(ExpectedQueryType.CHITCHAT):
            result = classify_query(query.text)
            assert result == QueryType.CHITCHAT, f"'{query.text}' should be CHITCHAT, got {result}"

    def test_chitchat_queries_have_responses(self):
        """All CHITCHAT queries should have canned responses."""
        for query in get_queries_by_type(ExpectedQueryType.CHITCHAT):
            response = get_chitchat_response(query.text)
            assert response is not None, f"'{query.text}' should have a canned response"

    def test_simple_queries_not_chitchat(self):
        """SIMPLE queries should not be classified as CHITCHAT."""
        for query in get_queries_by_type(ExpectedQueryType.SIMPLE):
            result = classify_query(query.text)
            assert result != QueryType.CHITCHAT, f"'{query.text}' should not be CHITCHAT"

    def test_complex_queries_classified_as_complex(self):
        """COMPLEX queries should be classified as COMPLEX."""
        for query in get_queries_by_type(ExpectedQueryType.COMPLEX):
            result = classify_query(query.text)
            assert result == QueryType.COMPLEX, f"'{query.text}' should be COMPLEX, got {result}"

    def test_all_queries_routable(self):
        """All 20 queries should be routable without errors."""
        for query in SMOKE_QUERIES:
            result = classify_query(query.text)
            assert result in QueryType
