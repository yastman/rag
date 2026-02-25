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
