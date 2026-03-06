"""Tests for demo search — text and voice input → results."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.handlers.demo_handler import handle_demo_search_text
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
)


class TestDemoSearchText:
    @pytest.mark.asyncio
    async def test_extracts_and_searches(self) -> None:
        message = AsyncMock()
        message.text = "двушка до 100к"
        state = AsyncMock()

        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )

        apartments_service = AsyncMock()
        apartments_service.search_with_filters.return_value = (
            [
                {
                    "complex_name": "Test",
                    "rooms": 2,
                    "price_eur": 95000,
                    "area_m2": 60,
                    "city": "Солнечный берег",
                }
            ],
            1,
        )

        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert.return_value = (
            [0.1] * 1024,
            {"idx": [1]},
            [[0.1] * 128],
        )

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
            embeddings=embeddings,
        )
        pipeline.extract.assert_awaited_once_with("двушка до 100к")
        message.answer.assert_awaited()

    @pytest.mark.asyncio
    async def test_low_confidence_still_searches(self) -> None:
        message = AsyncMock()
        message.text = "что-нибудь красивое"
        state = AsyncMock()

        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            meta=ExtractionMeta(source="llm", confidence="LOW"),
        )

        apartments_service = AsyncMock()
        apartments_service.search_with_filters.return_value = ([], 0)

        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert.return_value = (
            [0.1] * 1024,
            {"idx": [1]},
            [[0.1] * 128],
        )

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
            embeddings=embeddings,
        )
        apartments_service.search_with_filters.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_pipeline_returns_error(self) -> None:
        message = AsyncMock()
        message.text = "двушка"
        state = AsyncMock()

        await handle_demo_search_text(message, state, pipeline=None)
        message.answer.assert_awaited_once()
        args = message.answer.await_args.args[0]
        assert "недоступен" in args


class TestDemoSearchEdgeCases:
    @pytest.mark.asyncio
    async def test_no_text_returns_prompt(self) -> None:
        """Empty text message shows guidance."""
        message = AsyncMock()
        message.text = None
        state = AsyncMock()
        await handle_demo_search_text(message, state, pipeline=AsyncMock())
        args = message.answer.await_args.args[0]
        assert "текстовое" in args

    @pytest.mark.asyncio
    async def test_no_embeddings_shows_extraction(self) -> None:
        """Pipeline works but no embeddings — shows extracted filters."""
        message = AsyncMock()
        message.text = "двушка до 100к"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=None,
            embeddings=None,
        )
        calls = [c.args[0] for c in message.answer.await_args_list]
        assert any("Распознано" in c or "тестовом" in c for c in calls)

    @pytest.mark.asyncio
    async def test_empty_results_shows_not_found(self) -> None:
        """Search returns 0 results — shows 'not found' message."""
        message = AsyncMock()
        message.text = "пентхаус в Бургасе"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        apartments_service = AsyncMock()
        apartments_service.search_with_filters.return_value = ([], 0)
        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
            embeddings=embeddings,
        )
        calls = [c.args[0] for c in message.answer.await_args_list]
        assert any("не найдено" in c for c in calls)

    @pytest.mark.asyncio
    async def test_results_formatted_with_details(self) -> None:
        """Search results include complex name, rooms, price, area."""
        message = AsyncMock()
        message.text = "двушка"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        apartments_service = AsyncMock()
        apartments_service.search_with_filters.return_value = (
            [
                {
                    "complex_name": "Fort Beach",
                    "rooms": 2,
                    "price_eur": 95000,
                    "area_m2": 60,
                    "city": "Солнечный берег",
                }
            ],
            1,
        )
        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
            embeddings=embeddings,
        )
        calls = [c.args[0] for c in message.answer.await_args_list]
        result_msg = [c for c in calls if "Fort Beach" in c]
        assert len(result_msg) == 1
        assert "комн." in result_msg[0]
        assert "м²" in result_msg[0]


class TestDemoVoice:
    @pytest.mark.asyncio
    async def test_voice_transcribed_and_searched(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_search_voice

        message = AsyncMock()
        message.voice = AsyncMock()
        message.text = None
        state = AsyncMock()

        with patch("telegram_bot.handlers.demo_handler.transcribe_voice") as mock_stt:
            mock_stt.return_value = "двушка до 100к"
            pipeline = AsyncMock()
            pipeline.extract.return_value = ApartmentSearchFilters(
                hard=HardFilters(rooms=2, max_price_eur=100000),
                meta=ExtractionMeta(source="llm", confidence="HIGH"),
            )
            apartments_service = AsyncMock()
            apartments_service.search_with_filters.return_value = ([], 0)
            embeddings = AsyncMock()
            embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

            await handle_demo_search_voice(
                message,
                state,
                pipeline=pipeline,
                apartments_service=apartments_service,
                embeddings=embeddings,
            )
            mock_stt.assert_awaited_once()
            pipeline.extract.assert_awaited_once_with("двушка до 100к")

    @pytest.mark.asyncio
    async def test_voice_stt_fails_shows_error(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_search_voice

        message = AsyncMock()
        message.voice = AsyncMock()
        state = AsyncMock()

        with patch("telegram_bot.handlers.demo_handler.transcribe_voice") as mock_stt:
            mock_stt.return_value = None
            await handle_demo_search_voice(message, state, pipeline=AsyncMock())
            calls = [c.args[0] for c in message.answer.await_args_list]
            assert any("распознать" in c for c in calls)


class TestDemoApartmentsWithDynamicExamples:
    @pytest.mark.asyncio
    async def test_dynamic_examples_from_service(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_apartments

        callback = AsyncMock()
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        state = AsyncMock()

        apartments_service = AsyncMock()
        apartments_service.get_collection_stats.return_value = {
            "cities": ["Солнечный берег", "Свети Влас", "Элените"],
            "complexes": ["Premier Fort Beach"],
            "rooms": [1, 2, 3],
            "min_price": 69500,
            "max_price": 314000,
        }
        await handle_demo_apartments(callback, state, apartments_service=apartments_service)
        state.update_data.assert_awaited_once()
        saved = state.update_data.await_args.kwargs.get("examples")
        assert saved is not None
        assert len(saved) == 4
        assert any("Солнечный берег" in e or "Premier Fort" in e for e in saved)

    @pytest.mark.asyncio
    async def test_dynamic_examples_fallback_on_error(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_apartments
        from telegram_bot.keyboards.demo_keyboard import DEFAULT_EXAMPLES

        callback = AsyncMock()
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        state = AsyncMock()

        apartments_service = AsyncMock()
        apartments_service.get_collection_stats.side_effect = RuntimeError("Qdrant down")
        await handle_demo_apartments(callback, state, apartments_service=apartments_service)
        saved = state.update_data.await_args.kwargs.get("examples")
        assert saved == DEFAULT_EXAMPLES
