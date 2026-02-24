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
