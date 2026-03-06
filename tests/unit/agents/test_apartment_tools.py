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


# ---------------------------------------------------------------------------
# BotContext field
# ---------------------------------------------------------------------------


def test_bot_context_has_apartment_pipeline_field() -> None:
    """BotContext.apartment_pipeline exists and defaults to None."""
    from telegram_bot.agents.context import BotContext

    ctx = BotContext(
        telegram_user_id=1,
        session_id="s",
        language="ru",
        kommo_client=None,
        history_service=MagicMock(),
        embeddings=MagicMock(),
        sparse_embeddings=MagicMock(),
        qdrant=MagicMock(),
        cache=MagicMock(),
        reranker=None,
        llm=MagicMock(),
    )
    assert hasattr(ctx, "apartment_pipeline")
    assert ctx.apartment_pipeline is None


# ---------------------------------------------------------------------------
# Pipeline fallback in apartment_search
# ---------------------------------------------------------------------------


class TestPipelineFallback:
    """apartment_search pipeline fallback: extract filters from query when none explicit."""

    def _make_ctx(self, pipeline=None):
        ctx = MagicMock()
        ctx.apartments_service = AsyncMock()
        ctx.apartments_service.search_with_filters.return_value = ([], 0)
        ctx.cache = AsyncMock()
        ctx.embeddings = AsyncMock()
        ctx.embeddings.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}, None)
        )
        ctx.apartment_pipeline = pipeline
        ctx.search_event_store = None
        return ctx

    def _make_extraction(
        self,
        rooms=None,
        min_price_eur=None,
        max_price_eur=None,
        semantic_remainder=None,
        view_tags=None,
    ):
        extraction = MagicMock()
        extraction.hard.rooms = rooms
        extraction.hard.min_price_eur = min_price_eur
        extraction.hard.max_price_eur = max_price_eur
        extraction.hard.min_area_m2 = None
        extraction.hard.max_area_m2 = None
        extraction.hard.min_floor = None
        extraction.hard.max_floor = None
        extraction.hard.complex_name = None
        extraction.hard.is_furnished = None
        extraction.hard.view_tags = view_tags or []
        extraction.meta.semantic_remainder = semantic_remainder
        return extraction

    @pytest.mark.asyncio
    async def test_pipeline_fallback_extracts_filters(self) -> None:
        """Pipeline extracts rooms/price from query when no explicit filters provided."""
        pipeline = AsyncMock()
        extraction = self._make_extraction(rooms=2, max_price_eur=200000)
        pipeline.extract.return_value = extraction

        ctx = self._make_ctx(pipeline=pipeline)
        config = {"configurable": {"bot_context": ctx}}
        await apartment_search.ainvoke({"query": "двушка до 200к"}, config=config)

        pipeline.extract.assert_awaited_once_with("двушка до 200к")
        call_kwargs = ctx.apartments_service.search_with_filters.await_args
        filters = call_kwargs.kwargs["filters"]
        assert filters["rooms"] == 2
        assert filters["price_eur"]["lte"] == 200000

    @pytest.mark.asyncio
    async def test_pipeline_fallback_skipped_with_explicit_filters(self) -> None:
        """Pipeline is NOT called when rooms is already provided as explicit arg."""
        pipeline = AsyncMock()
        ctx = self._make_ctx(pipeline=pipeline)
        config = {"configurable": {"bot_context": ctx}}

        await apartment_search.ainvoke({"query": "двушка", "rooms": 2}, config=config)

        pipeline.extract.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_fallback_uses_semantic_remainder(self) -> None:
        """semantic_remainder from extraction replaces original query for embedding."""
        pipeline = AsyncMock()
        extraction = self._make_extraction(rooms=1, semantic_remainder="у моря")
        pipeline.extract.return_value = extraction

        ctx = self._make_ctx(pipeline=pipeline)
        config = {"configurable": {"bot_context": ctx}}
        await apartment_search.ainvoke({"query": "однушка у моря"}, config=config)

        ctx.embeddings.aembed_hybrid_with_colbert.assert_awaited_once_with("у моря")

    @pytest.mark.asyncio
    async def test_pipeline_fallback_error_continues_without_filters(self) -> None:
        """When pipeline raises, search continues with original query and no extracted filters."""
        pipeline = AsyncMock()
        pipeline.extract.side_effect = RuntimeError("Pipeline broken")

        ctx = self._make_ctx(pipeline=pipeline)
        config = {"configurable": {"bot_context": ctx}}

        # Must not raise; search proceeds normally
        result = await apartment_search.ainvoke({"query": "студия"}, config=config)

        ctx.embeddings.aembed_hybrid_with_colbert.assert_awaited_once_with("студия")
        call_kwargs = ctx.apartments_service.search_with_filters.await_args
        # No filters extracted → filters dict is empty → passed as None
        assert call_kwargs.kwargs.get("filters") is None
        assert "ошибка" not in result.lower()

    @pytest.mark.asyncio
    async def test_pipeline_fallback_none_when_no_pipeline(self) -> None:
        """When ctx.apartment_pipeline is None, search runs without any extraction."""
        ctx = self._make_ctx(pipeline=None)
        config = {"configurable": {"bot_context": ctx}}

        await apartment_search.ainvoke({"query": "апартаменты"}, config=config)

        ctx.embeddings.aembed_hybrid_with_colbert.assert_awaited_once_with("апартаменты")
        call_kwargs = ctx.apartments_service.search_with_filters.await_args
        assert call_kwargs.kwargs.get("filters") is None
