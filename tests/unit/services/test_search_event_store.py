"""Tests for SearchEventStore."""

from __future__ import annotations

from unittest.mock import AsyncMock

from telegram_bot.services.search_event_store import SearchEventStore, _format_filters


class TestFormatFilters:
    """Unit tests for the _format_filters helper."""

    def test_price_range_with_zero_lower_bound(self) -> None:
        """price_eur with gte=0 must not be silently dropped (0 is falsy in Python).

        Edge case: `if lo and hi` evaluates `0 and 50000` as False when lo=0,
        causing the range to be silently omitted.  The correct output is '€0–€50,000'.
        """
        result = _format_filters({"price_eur": {"gte": 0, "lte": 50000}})
        assert "€0" in result, f"Expected '€0' in result, got: {result!r}"
        assert "50,000" in result, f"Expected '50,000' in result, got: {result!r}"

    def test_price_range_normal(self) -> None:
        """Normal price range renders correctly."""
        result = _format_filters({"price_eur": {"gte": 30000, "lte": 80000}})
        assert "30,000" in result
        assert "80,000" in result

    def test_price_only_upper_bound(self) -> None:
        result = _format_filters({"price_eur": {"lte": 100000}})
        assert "до" in result
        assert "100,000" in result

    def test_price_only_lower_bound(self) -> None:
        result = _format_filters({"price_eur": {"gte": 50000}})
        assert "от" in result
        assert "50,000" in result

    def test_empty_filters_returns_empty_string(self) -> None:
        assert _format_filters({}) == ""
        assert _format_filters(None) == ""

    def test_rooms_filter(self) -> None:
        result = _format_filters({"rooms": 2})
        assert "2 комн." in result

    def test_json_string_input(self) -> None:
        """_format_filters accepts a JSON string (as returned from DB)."""
        import json

        raw = json.dumps({"rooms": 3, "price_eur": {"gte": 40000, "lte": 90000}})
        result = _format_filters(raw)
        assert "3 комн." in result
        assert "40,000" in result


class TestSearchEventStoreAppend:
    async def test_append_inserts_row(self) -> None:
        pool = AsyncMock()
        store = SearchEventStore(pool=pool)

        await store.append(
            user_id=123,
            session_id="chat:123",
            query="двушка у моря",
            filters={"rooms": 2, "price_eur": {"lte": 150000}},
            results_count=12,
        )

        pool.execute.assert_called_once()
        args = pool.execute.call_args
        assert args[0][1] == 123  # user_id
        assert args[0][2] == "chat:123"  # session_id
        assert args[0][4] == "двушка у моря"  # query
        assert "rooms" in args[0][5]  # filters JSON

    async def test_append_with_no_filters(self) -> None:
        pool = AsyncMock()
        store = SearchEventStore(pool=pool)

        await store.append(
            user_id=123,
            session_id="chat:123",
            query="покажи квартиры",
        )

        pool.execute.assert_called_once()
        args = pool.execute.call_args
        assert args[0][5] is None  # filters = None
        assert args[0][6] == 0  # results_count default


class TestSearchEventStoreGet:
    async def test_get_user_events_returns_rows(self) -> None:
        pool = AsyncMock()
        pool.fetch = AsyncMock(
            return_value=[
                {
                    "event_type": "apartment_search",
                    "query": "двушка у моря",
                    "filters": '{"rooms": 2}',
                    "results_count": 12,
                    "created_at": "2026-03-03 14:20:00+00",
                },
                {
                    "event_type": "apartment_search",
                    "query": "студия в Premier Fort",
                    "filters": '{"complex_name": "Premier Fort Beach"}',
                    "results_count": 8,
                    "created_at": "2026-03-03 14:25:00+00",
                },
            ]
        )
        store = SearchEventStore(pool=pool)

        events = await store.get_user_events(user_id=123, limit=20)

        assert len(events) == 2
        assert events[0]["query"] == "двушка у моря"
        pool.fetch.assert_called_once()
        # Verify user_id passed to query
        args = pool.fetch.call_args
        assert args[0][1] == 123

    async def test_get_user_events_empty(self) -> None:
        pool = AsyncMock()
        pool.fetch = AsyncMock(return_value=[])
        store = SearchEventStore(pool=pool)

        events = await store.get_user_events(user_id=999)

        assert events == []
