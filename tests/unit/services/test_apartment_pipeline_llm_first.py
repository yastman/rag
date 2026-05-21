"""Tests for the regex-first hybrid apartment extraction pipeline.

The pipeline runs regex first for deterministic numeric filters, then asks the
LLM to fill gaps, and merges the two results via ``merge_extraction_results``
(see issue #1609). When both regex and LLM participate, the merged result
carries ``meta.source == "hybrid"``. Regex-only / LLM-error / cache paths keep
their original sources.
"""

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
    """Regex runs first; LLM fills gaps; results are merged into a hybrid source."""

    @pytest.mark.asyncio
    async def test_llm_participates_in_hybrid_merge(self, pipeline, mock_llm) -> None:
        """LLM is invoked for gap-fill and the merged result reports source=hybrid.

        After the regex-first hybrid merge introduced in #1609, the pipeline no
        longer returns the raw LLM result: it merges regex (deterministic
        numeric floor) with the LLM result and stamps ``source="hybrid"`` via
        ``merge_extraction_results``. The test verifies that:

        * the LLM does participate (``assert_awaited_once``);
        * the merged result reports ``source == "hybrid"``;
        * regex wins for numeric fields — the regex value (``rooms=3``) is
          preserved over the LLM's ``rooms=2``, which guards the #1609 contract.
        """
        result = await pipeline.extract("двушка в солнечном береге до 100к")
        mock_llm.extract.assert_awaited_once()
        assert result.meta.source == "hybrid"
        # Regex-wins-on-numeric: regex extracts rooms=3 from this query and
        # must override the LLM's rooms=2 in the merged result.
        assert result.hard.rooms == 3

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
