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
