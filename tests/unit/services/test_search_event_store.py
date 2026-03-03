"""Tests for SearchEventStore."""

from __future__ import annotations

from unittest.mock import AsyncMock

from telegram_bot.services.search_event_store import SearchEventStore


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
