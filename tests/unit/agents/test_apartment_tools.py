"""Tests for apartment_search @tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.agents.apartment_tools import apartment_search


class TestApartmentSearchTool:
    @pytest.mark.asyncio
    async def test_returns_formatted_results(self) -> None:
        mock_service = AsyncMock()
        mock_service.search_with_filters.return_value = (
            [
                {
                    "score": 0.85,
                    "payload": {
                        "complex_name": "Premier Fort Beach",
                        "apartment_number": "248",
                        "rooms": 2,
                        "floor": 4,
                        "area_m2": 78.66,
                        "view_primary": "sea",
                        "price_eur": 215000.0,
                    },
                },
            ],
            1,
        )

        ctx = MagicMock()
        ctx.apartments_service = mock_service
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}, [[0.1] * 1024])
        )

        config = {"configurable": {"bot_context": ctx}}
        result = await apartment_search.ainvoke(
            {"query": "двушка до 200к", "rooms": 2, "max_price_eur": 200000},
            config=config,
        )

        assert "Premier Fort Beach" in result
        assert "215" in result
        assert "248" in result

    @pytest.mark.asyncio
    async def test_no_results(self) -> None:
        mock_service = AsyncMock()
        mock_service.search_with_filters.return_value = ([], 0)

        ctx = MagicMock()
        ctx.apartments_service = mock_service
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [], "values": []}, [])
        )

        config = {"configurable": {"bot_context": ctx}}
        result = await apartment_search.ainvoke(
            {"query": "пентхаус на крыше"},
            config=config,
        )

        assert "нет" in result.lower() or "не найден" in result.lower()

    @pytest.mark.asyncio
    async def test_caches_embeddings_after_compute(self) -> None:
        """Verify cache.store_embedding and store_sparse_embedding are called (#635)."""
        dense = [0.1] * 1024
        sparse = {"indices": [1], "values": [0.5]}
        colbert = [[0.1] * 1024]

        mock_service = AsyncMock()
        mock_service.search_with_filters.return_value = ([], 0)

        ctx = MagicMock()
        ctx.apartments_service = mock_service
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(return_value=(dense, sparse, colbert))

        config = {"configurable": {"bot_context": ctx}}
        await apartment_search.ainvoke(
            {"query": "студия у моря"},
            config=config,
        )

        ctx.cache.store_embedding.assert_awaited_once_with("студия у моря", dense)
        ctx.cache.store_sparse_embedding.assert_awaited_once_with("студия у моря", sparse)

    @pytest.mark.asyncio
    async def test_cache_store_failure_returns_error_message(self) -> None:
        """If cache store raises, the outer try/except catches and returns error."""
        ctx = MagicMock()
        ctx.apartments_service = AsyncMock()
        ctx.cache = AsyncMock()
        ctx.cache.store_embedding = AsyncMock(side_effect=RuntimeError("Redis down"))
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [], "values": []}, [])
        )

        config = {"configurable": {"bot_context": ctx}}
        result = await apartment_search.ainvoke(
            {"query": "любая квартира"},
            config=config,
        )

        assert "ошибка" in result.lower()

    async def test_search_logs_filters_to_store(self) -> None:
        mock_service = AsyncMock()
        mock_service.search_with_filters.return_value = (
            [
                {
                    "score": 0.85,
                    "payload": {
                        "complex_name": "PFB",
                        "apartment_number": "1",
                        "rooms": 2,
                        "floor": 3,
                        "area_m2": 60,
                        "price_eur": 100000,
                    },
                }
            ],
            1,
        )

        mock_store = AsyncMock()
        ctx = MagicMock()
        ctx.apartments_service = mock_service
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}, [[0.1] * 1024])
        )
        ctx.telegram_user_id = 42
        ctx.session_id = "chat:42"
        ctx.search_event_store = mock_store

        config = {"configurable": {"bot_context": ctx}}
        await apartment_search.ainvoke(
            {"query": "двушка", "rooms": 2, "max_price_eur": 150000},
            config=config,
        )

        mock_store.append.assert_called_once()
        call_kwargs = mock_store.append.call_args
        assert call_kwargs[1]["user_id"] == 42
        assert call_kwargs[1]["query"] == "двушка"
        assert call_kwargs[1]["filters"]["rooms"] == 2
        assert call_kwargs[1]["results_count"] == 1

    async def test_search_works_without_store(self) -> None:
        """Store=None не ломает поиск."""
        mock_service = AsyncMock()
        mock_service.search_with_filters.return_value = ([], 0)

        ctx = MagicMock()
        ctx.apartments_service = mock_service
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}, None)
        )
        ctx.search_event_store = None

        config = {"configurable": {"bot_context": ctx}}
        result = await apartment_search.ainvoke({"query": "test"}, config=config)

        assert "не найдены" in result

    async def test_store_error_does_not_break_search(self) -> None:
        """Ошибка store не блокирует ответ."""
        mock_service = AsyncMock()
        mock_service.search_with_filters.return_value = (
            [
                {
                    "score": 0.8,
                    "payload": {
                        "complex_name": "X",
                        "apartment_number": "1",
                        "rooms": 1,
                        "floor": 1,
                        "area_m2": 40,
                        "price_eur": 50000,
                    },
                }
            ],
            1,
        )

        mock_store = AsyncMock()
        mock_store.append.side_effect = Exception("DB down")
        ctx = MagicMock()
        ctx.apartments_service = mock_service
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}, None)
        )
        ctx.search_event_store = mock_store

        config = {"configurable": {"bot_context": ctx}}
        result = await apartment_search.ainvoke({"query": "test"}, config=config)

        assert "X" in result  # поиск прошёл несмотря на ошибку store
