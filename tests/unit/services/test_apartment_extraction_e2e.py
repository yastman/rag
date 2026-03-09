"""E2E integration tests for the full extraction pipeline (no LLM mocking)."""

from __future__ import annotations

import pytest

from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline
from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor


@pytest.fixture
def pipeline() -> ApartmentExtractionPipeline:
    return ApartmentExtractionPipeline(regex_extractor=ApartmentFilterExtractor())


class TestE2ERegexOnlyPipeline:
    """Full pipeline with regex extractor only (no LLM, no Redis)."""

    async def test_sunny_beach_2rooms_price_range(
        self, pipeline: ApartmentExtractionPipeline
    ) -> None:
        result = await pipeline.extract("двушка солнечный берег от 50000 до 200000")
        assert result.hard.rooms == 2
        assert result.hard.city == "Солнечный берег"
        assert result.hard.min_price_eur == 50000
        assert result.hard.max_price_eur == 200000
        assert result.meta.confidence in ("HIGH", "MEDIUM")

    async def test_sveti_vlas_3rooms(self, pipeline: ApartmentExtractionPipeline) -> None:
        result = await pipeline.extract("трешка свети влас")
        assert result.hard.rooms == 3
        assert result.hard.city == "Свети Влас"
        assert result.meta.confidence in ("HIGH", "MEDIUM")

    async def test_elenite_price_only(self, pipeline: ApartmentExtractionPipeline) -> None:
        result = await pipeline.extract("элените до 150000")
        assert result.hard.city == "Элените"
        assert result.hard.max_price_eur == 150000
        assert result.meta.confidence in ("HIGH", "MEDIUM")

    async def test_no_filters_gives_low_confidence(
        self, pipeline: ApartmentExtractionPipeline
    ) -> None:
        result = await pipeline.extract("хочу квартиру у моря")
        assert result.meta.confidence == "LOW"

    async def test_complex_name_extracted(self, pipeline: ApartmentExtractionPipeline) -> None:
        result = await pipeline.extract("апартаменты в Premier Fort Beach")
        assert result.hard.complex_name is not None
        assert "Premier Fort Beach" in (result.hard.complex_name or "")
        assert result.meta.confidence in ("HIGH", "MEDIUM")

    async def test_floor_extracted(self, pipeline: ApartmentExtractionPipeline) -> None:
        result = await pipeline.extract("квартира 5 этаж")
        assert result.hard.min_floor == 5 or result.hard.max_floor == 5

    async def test_returns_apartment_search_filters_type(
        self, pipeline: ApartmentExtractionPipeline
    ) -> None:
        from telegram_bot.services.apartment_models import ApartmentSearchFilters

        result = await pipeline.extract("двушка")
        assert isinstance(result, ApartmentSearchFilters)

    async def test_city_alias_sunny_beach_en(self, pipeline: ApartmentExtractionPipeline) -> None:
        result = await pipeline.extract("квартира в sunny beach")
        assert result.hard.city == "Солнечный берег"

    async def test_city_alias_sveti_vlas_ru(self, pipeline: ApartmentExtractionPipeline) -> None:
        result = await pipeline.extract("апартаменты святой влас")
        assert result.hard.city == "Свети Влас"

    async def test_hard_filters_to_filters_dict(
        self, pipeline: ApartmentExtractionPipeline
    ) -> None:
        result = await pipeline.extract("двушка солнечный берег до 200000")
        filters = result.hard.to_filters_dict()
        assert filters is not None
        assert filters.get("rooms") == 2
        assert filters.get("price_eur", {}).get("lte") == 200000
