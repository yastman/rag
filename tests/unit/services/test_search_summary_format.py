"""Tests for format_search_summary."""

from __future__ import annotations

from datetime import UTC, datetime

from telegram_bot.services.search_event_store import format_search_summary


class TestFormatSearchSummary:
    def test_formats_multiple_events(self) -> None:
        events = [
            {
                "query": "двушка у моря до 150к",
                "filters": {"rooms": 2, "price_eur": {"lte": 150000}, "view_tags": ["sea"]},
                "results_count": 12,
                "created_at": datetime(2026, 3, 3, 14, 20, tzinfo=UTC),
            },
            {
                "query": "студия в Premier Fort",
                "filters": {"complex_name": "Premier Fort Beach"},
                "results_count": 8,
                "created_at": datetime(2026, 3, 3, 14, 25, tzinfo=UTC),
            },
        ]

        result = format_search_summary(events)

        assert "2 запроса" in result or "2 запрос" in result
        assert "двушка у моря до 150к" in result
        assert "студия в Premier Fort" in result
        assert "12" in result
        assert "8" in result

    def test_empty_events(self) -> None:
        result = format_search_summary([])
        assert result == ""

    def test_single_event_no_filters(self) -> None:
        events = [
            {
                "query": "покажи квартиры",
                "filters": None,
                "results_count": 25,
                "created_at": datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
            },
        ]

        result = format_search_summary(events)

        assert "покажи квартиры" in result
        assert "25" in result

    def test_filters_json_string_parsed(self) -> None:
        """Postgres может вернуть filters как JSON-строку."""
        events = [
            {
                "query": "test",
                "filters": '{"rooms": 3}',
                "results_count": 5,
                "created_at": datetime(2026, 3, 3, 10, 0, tzinfo=UTC),
            },
        ]

        result = format_search_summary(events)

        assert "3 комн" in result
