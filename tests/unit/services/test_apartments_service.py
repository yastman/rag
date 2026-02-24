"""Tests for ApartmentsService."""

from __future__ import annotations

from telegram_bot.services.apartments_service import (
    _build_apartment_filter,
    check_escalation,
)


class TestBuildApartmentFilter:
    """Test filter construction without metadata. prefix."""

    def test_exact_match(self) -> None:
        f = _build_apartment_filter({"rooms": 2, "complex_name": "Premier Fort Beach"})
        assert f is not None
        assert len(f.must) == 2

    def test_range_filter(self) -> None:
        f = _build_apartment_filter({"price_eur": {"gte": 100000, "lte": 200000}})
        assert f is not None
        assert len(f.must) == 1

    def test_view_tags_match_any(self) -> None:
        f = _build_apartment_filter({"view_tags": ["sea", "pool"]})
        assert f is not None
        # Should use MatchAny, not MatchValue
        condition = f.must[0]
        assert hasattr(condition, "match")

    def test_empty_returns_none(self) -> None:
        assert _build_apartment_filter({}) is None
        assert _build_apartment_filter(None) is None

    def test_no_metadata_prefix(self) -> None:
        f = _build_apartment_filter({"rooms": 2})
        # Key should be "rooms" not "metadata.rooms"
        assert f.must[0].key == "rooms"


class TestCheckEscalation:
    def test_no_escalation(self) -> None:
        assert not check_escalation(
            returned_count=5,
            top_k=10,
            score_spread=0.3,
            confidence="HIGH",
        )

    def test_escalate_zero_results(self) -> None:
        result = check_escalation(returned_count=0, top_k=10, score_spread=0, confidence="HIGH")
        assert result is not None
        assert "no_results" in result

    def test_escalate_wide_ambiguous_topk(self) -> None:
        result = check_escalation(
            returned_count=10,
            top_k=10,
            score_spread=0.001,
            confidence="MEDIUM",
        )
        assert result is not None
        assert "ambiguous_topk" in result

    def test_escalate_low_confidence(self) -> None:
        result = check_escalation(returned_count=5, top_k=10, score_spread=0.3, confidence="LOW")
        assert result is not None
        assert "low_confidence" in result
