"""Tests for ApartmentsService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.apartments_service import (
    ApartmentsService,
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

    def test_build_filter_is_furnished_true(self) -> None:
        f = _build_apartment_filter({"is_furnished": True})
        assert f is not None
        assert len(f.must) == 1
        assert f.must[0].key == "is_furnished"
        assert f.must[0].match.value is True

    def test_build_filter_is_furnished_false(self) -> None:
        f = _build_apartment_filter({"is_furnished": False})
        assert f is not None
        assert len(f.must) == 1
        assert f.must[0].key == "is_furnished"
        assert f.must[0].match.value is False

    def test_build_filter_is_promotion_true(self) -> None:
        f = _build_apartment_filter({"is_promotion": True})
        assert f is not None
        assert len(f.must) == 1
        assert f.must[0].key == "is_promotion"
        assert f.must[0].match.value is True

    def test_build_filter_combined_bool_and_range(self) -> None:
        """Bool must use MatchValue, not Range — isinstance(True, int) == True in Python."""
        f = _build_apartment_filter({"is_furnished": True, "price_eur": {"gte": 50000}})
        assert f is not None
        assert len(f.must) == 2
        # Bool condition should use MatchValue, not Range
        for cond in f.must:
            if cond.key == "is_furnished":
                assert cond.match is not None
                assert cond.match.value is True
                assert cond.range is None


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


class TestScrollWithFilters:
    """Test payload-only scroll without vectors."""

    @pytest.fixture
    def mock_qdrant(self) -> MagicMock:
        q = MagicMock()
        q.client = MagicMock()
        q.collection_name = "apartments"
        q.client.scroll = AsyncMock(return_value=([], None))
        q.client.count = AsyncMock(return_value=MagicMock(count=0))
        return q

    async def test_scroll_builds_rooms_filter(self, mock_qdrant: MagicMock) -> None:
        svc = ApartmentsService(mock_qdrant)
        await svc.scroll_with_filters({"rooms": 2})
        assert mock_qdrant.client.scroll.called
        call_kwargs = mock_qdrant.client.scroll.call_args.kwargs
        assert call_kwargs.get("scroll_filter") is not None

    async def test_scroll_returns_formatted_results(self, mock_qdrant: MagicMock) -> None:
        record = MagicMock()
        record.id = "abc-123"
        record.payload = {"rooms": 2, "price_eur": 150000.0, "complex_name": "Test"}
        mock_qdrant.client.scroll = AsyncMock(return_value=([record], None))
        mock_qdrant.client.count = AsyncMock(return_value=MagicMock(count=1))

        svc = ApartmentsService(mock_qdrant)
        results, total, _offset = await svc.scroll_with_filters({"rooms": 2})

        assert len(results) == 1
        assert results[0]["payload"]["rooms"] == 2
        assert results[0]["id"] == "abc-123"
        assert total == 1

    async def test_scroll_with_promotion_filter(self, mock_qdrant: MagicMock) -> None:
        svc = ApartmentsService(mock_qdrant)
        await svc.scroll_with_filters({"is_promotion": True})

        assert mock_qdrant.client.scroll.called
        call_kwargs = mock_qdrant.client.scroll.call_args.kwargs
        assert call_kwargs.get("scroll_filter") is not None

    async def test_scroll_no_filter_passes_none(self, mock_qdrant: MagicMock) -> None:
        svc = ApartmentsService(mock_qdrant)
        await svc.scroll_with_filters({})

        call_kwargs = mock_qdrant.client.scroll.call_args.kwargs
        assert call_kwargs.get("scroll_filter") is None

    async def test_scroll_returns_next_offset(self, mock_qdrant: MagicMock) -> None:
        mock_qdrant.client.scroll = AsyncMock(return_value=([], "offset-token"))
        svc = ApartmentsService(mock_qdrant)
        _, _, next_offset = await svc.scroll_with_filters({})
        assert next_offset == "offset-token"
