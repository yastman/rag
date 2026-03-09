"""Tests for ApartmentExtractionPipeline (LLM first, regex fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


def _make_filters(confidence: str = "HIGH", source: str = "regex") -> ApartmentSearchFilters:
    return ApartmentSearchFilters(
        hard=HardFilters(rooms=2, city="Солнечный берег"),
        soft=SoftPreferences(),
        meta=ExtractionMeta(source=source, confidence=confidence),
    )


def _make_regex_extractor(confidence: str = "HIGH") -> MagicMock:
    extractor = MagicMock()
    parsed = MagicMock()
    parsed.city = "Солнечный берег"
    parsed.rooms = 2
    parsed.complex_name = None
    parsed.min_price_eur = None
    parsed.max_price_eur = None
    parsed.min_area_m2 = None
    parsed.max_area_m2 = None
    parsed.min_floor = None
    parsed.max_floor = None
    parsed.view_tags = []
    parsed.is_furnished = None
    parsed.confidence = confidence
    parsed.score = 4
    parsed.conflicts = []
    parsed.missing_fields = []
    parsed.raw_query = "двушка солнечный берег"
    parsed.semantic_query = ""
    extractor.parse.return_value = parsed
    return extractor


class TestPipelineHighConfidence:
    async def test_high_confidence_returns_regex_result(self) -> None:
        regex = _make_regex_extractor("HIGH")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex)

        result = await pipeline.extract("двушка солнечный берег")

        assert result.meta.confidence == "HIGH"
        assert result.meta.source == "regex"
        assert result.hard.rooms == 2

    async def test_llm_called_first_regardless_of_regex_confidence(self) -> None:
        regex = _make_regex_extractor("HIGH")
        llm = AsyncMock()
        llm.extract = AsyncMock(return_value=_make_filters("HIGH", "llm"))
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, llm_extractor=llm)

        await pipeline.extract("двушка солнечный берег")

        llm.extract.assert_called_once()


class TestPipelineMediumConfidence:
    async def test_llm_called_without_partial_filters(self) -> None:
        """LLM-first: no partial_filters — LLM extracts from scratch."""
        regex = _make_regex_extractor("MEDIUM")
        llm_result = _make_filters("HIGH", "llm")
        llm = AsyncMock()
        llm.extract = AsyncMock(return_value=llm_result)

        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, llm_extractor=llm)
        result = await pipeline.extract("двушка")

        llm.extract.assert_called_once()
        call_kwargs = llm.extract.call_args
        partial = call_kwargs.kwargs.get("partial_filters")
        assert partial is None
        assert result.meta.source == "llm"

    async def test_medium_without_llm_returns_regex(self) -> None:
        regex = _make_regex_extractor("MEDIUM")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, llm_extractor=None)

        result = await pipeline.extract("двушка")

        assert result.meta.source == "regex"


class TestPipelineLowConfidence:
    async def test_low_calls_full_llm_extraction(self) -> None:
        regex = _make_regex_extractor("LOW")
        llm_result = _make_filters("HIGH", "llm")
        llm = AsyncMock()
        llm.extract = AsyncMock(return_value=llm_result)

        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, llm_extractor=llm)

        result = await pipeline.extract("хочу квартиру у моря")

        llm.extract.assert_called_once()
        # No partial_filters for LOW confidence
        call_kwargs = llm.extract.call_args
        partial = call_kwargs.kwargs.get("partial_filters") or (
            call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
        )
        assert partial is None
        assert result.meta.source == "llm"

    async def test_low_without_llm_returns_regex(self) -> None:
        regex = _make_regex_extractor("LOW")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, llm_extractor=None)

        result = await pipeline.extract("хочу квартиру")

        assert result.meta.source == "regex"


class TestPipelineCache:
    async def test_cache_hit_skips_regex(self) -> None:
        cached = _make_filters("HIGH", "regex")
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=cached.model_dump_json())

        regex = _make_regex_extractor("HIGH")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, redis=redis)

        result = await pipeline.extract("двушка солнечный берег")

        regex.parse.assert_not_called()
        assert result.hard.rooms == 2

    async def test_cache_miss_runs_regex(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        regex = _make_regex_extractor("HIGH")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, redis=redis)

        await pipeline.extract("двушка солнечный берег")

        regex.parse.assert_called_once()

    async def test_llm_result_is_cached(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        regex = _make_regex_extractor("LOW")
        llm_result = _make_filters("HIGH", "llm")
        llm = AsyncMock()
        llm.extract = AsyncMock(return_value=llm_result)

        pipeline = ApartmentExtractionPipeline(
            regex_extractor=regex, llm_extractor=llm, redis=redis
        )

        await pipeline.extract("хочу квартиру у моря")

        redis.set.assert_called_once()

    async def test_no_redis_no_error(self) -> None:
        regex = _make_regex_extractor("HIGH")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, redis=None)

        result = await pipeline.extract("двушка")

        assert result is not None

    async def test_cache_corrupt_data_falls_through(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"not valid json {{{")

        regex = _make_regex_extractor("HIGH")
        pipeline = ApartmentExtractionPipeline(regex_extractor=regex, redis=redis)

        # Should not raise, should fall through to regex
        result = await pipeline.extract("двушка солнечный берег")

        regex.parse.assert_called_once()
        assert result is not None


class TestExtractionPipelineObservability:
    def test_extract_is_observed(self) -> None:
        """ApartmentExtractionPipeline.extract must be @observe-decorated (span: apartment-extraction-pipeline)."""
        assert hasattr(ApartmentExtractionPipeline.extract, "__wrapped__"), (
            "ApartmentExtractionPipeline.extract must be decorated with "
            "@observe(name='apartment-extraction-pipeline')"
        )
