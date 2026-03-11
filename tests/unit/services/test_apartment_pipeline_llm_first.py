"""Tests for LLM-first extraction pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline
from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
)


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    result = ApartmentSearchFilters(
        hard=HardFilters(rooms=2, city="Солнечный берег", max_price_eur=100000),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )
    llm.extract.return_value = result
    return llm


@pytest.fixture
def pipeline(mock_llm):
    return ApartmentExtractionPipeline(
        regex_extractor=ApartmentFilterExtractor(),
        llm_extractor=mock_llm,
    )


class TestLlmFirstPipeline:
    """LLM is called first, regex is fallback."""

    @pytest.mark.asyncio
    async def test_llm_called_first(self, pipeline, mock_llm) -> None:
        result = await pipeline.extract("двушка в солнечном береге до 100к")
        mock_llm.extract.assert_awaited_once()
        assert result.meta.source == "llm"
        assert result.hard.rooms == 2

    @pytest.mark.asyncio
    async def test_regex_fallback_on_llm_error(self, pipeline, mock_llm) -> None:
        mock_llm.extract.side_effect = RuntimeError("LLM unavailable")
        result = await pipeline.extract("двушка до 100000")
        assert result.meta.source == "regex"
        assert result.hard.rooms == 3

    @pytest.mark.asyncio
    async def test_cache_hit_skips_llm(self, mock_llm) -> None:
        redis = AsyncMock()
        cached = ApartmentSearchFilters(
            hard=HardFilters(rooms=3),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        redis.get.return_value = cached.model_dump_json()
        pipe = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=mock_llm,
            redis=redis,
        )
        result = await pipe.extract("трешка")
        mock_llm.extract.assert_not_awaited()
        assert result.hard.rooms == 3

    @pytest.mark.asyncio
    async def test_no_llm_uses_regex(self) -> None:
        pipe = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
        )
        result = await pipe.extract("двушка до 100000")
        assert result.meta.source == "regex"
        assert result.hard.rooms == 3

    @pytest.mark.asyncio
    async def test_llm_result_cached(self, mock_llm) -> None:
        redis = AsyncMock()
        redis.get.return_value = None
        pipe = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=mock_llm,
            redis=redis,
        )
        await pipe.extract("двушка")
        redis.set.assert_awaited_once()
