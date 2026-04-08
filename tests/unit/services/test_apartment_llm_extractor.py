"""Tests for Instructor-based LLM apartment filter extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.apartment_llm_extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    ApartmentLlmExtractor,
    _get_system_prompt,
    merge_extraction_results,
)
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


@pytest.fixture
def mock_llm_result() -> ApartmentSearchFilters:
    return ApartmentSearchFilters(
        hard=HardFilters(city="Солнечный берег", rooms=2, max_price_eur=100000),
        soft=SoftPreferences(near_sea=True),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )


class TestApartmentLlmExtractor:
    def test_system_prompt_contains_cities(self) -> None:
        assert "Солнечный берег" in EXTRACTION_SYSTEM_PROMPT
        assert "Свети Влас" in EXTRACTION_SYSTEM_PROMPT
        assert "Элените" in EXTRACTION_SYSTEM_PROMPT

    def test_system_prompt_contains_complexes(self) -> None:
        assert "Premier Fort Beach" in EXTRACTION_SYSTEM_PROMPT
        assert "Messambria Fort Beach" in EXTRACTION_SYSTEM_PROMPT

    async def test_extract_full_sets_source_llm(
        self, mock_llm_result: ApartmentSearchFilters
    ) -> None:
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=mock_llm_result)
        extractor._model = "gpt-4o-mini"

        result = await extractor.extract(query="просторная у моря")
        assert result.meta.source == "llm"

    async def test_extract_partial_sets_source_hybrid(
        self, mock_llm_result: ApartmentSearchFilters
    ) -> None:
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=mock_llm_result)
        extractor._model = "gpt-4o-mini"

        partial = HardFilters(rooms=2)
        result = await extractor.extract(query="солнечный берег", partial_filters=partial)
        assert result.meta.source == "hybrid"

    async def test_invalid_city_cleared(self) -> None:
        # Bypass Literal validation to emulate malformed LLM output.
        bad_result = ApartmentSearchFilters.model_construct(
            hard=HardFilters.model_construct(city="Бургас", rooms=2),
            meta=ExtractionMeta(source="llm"),
        )
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=bad_result)
        extractor._model = "gpt-4o-mini"

        result = await extractor.extract(query="квартира в бургасе")
        assert result.hard.city is None  # очищено post-validation

    async def test_valid_city_preserved(self, mock_llm_result: ApartmentSearchFilters) -> None:
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=mock_llm_result)
        extractor._model = "gpt-4o-mini"

        result = await extractor.extract(query="солнечный берег двушка")
        assert result.hard.city == "Солнечный берег"

    async def test_extract_coerces_null_view_tags_from_llm(self) -> None:
        bad_result = ApartmentSearchFilters.model_construct(
            hard=HardFilters.model_construct(view_tags=None),
            meta=ExtractionMeta(source="llm"),
        )
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=bad_result)
        extractor._model = "gpt-4o-mini"

        result = await extractor.extract(query="квартира без уточнения вида")
        assert result.hard.view_tags == []


class TestMergeExtractionResults:
    def test_regex_wins_for_numbers(self) -> None:
        regex = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="regex"),
        )
        llm = ApartmentSearchFilters(
            hard=HardFilters(rooms=3, max_price_eur=150000, city="Солнечный берег"),
            soft=SoftPreferences(near_sea=True),
            meta=ExtractionMeta(source="llm"),
        )
        merged = merge_extraction_results(regex, llm)
        assert merged.hard.rooms == 2  # regex wins
        assert merged.hard.max_price_eur == 100000  # regex wins
        assert merged.hard.city == "Солнечный берег"  # LLM fills gap
        assert merged.soft.near_sea is True  # LLM preferences
        assert merged.meta.source == "hybrid"

    def test_llm_fills_gaps(self) -> None:
        regex = ApartmentSearchFilters(
            hard=HardFilters(rooms=2),
            meta=ExtractionMeta(source="regex"),
        )
        llm = ApartmentSearchFilters(
            hard=HardFilters(city="Элените", complex_name="Premier Fort Beach"),
            meta=ExtractionMeta(source="llm"),
        )
        merged = merge_extraction_results(regex, llm)
        assert merged.hard.rooms == 2  # regex
        assert merged.hard.city == "Элените"  # LLM
        assert merged.hard.complex_name == "Premier Fort Beach"  # LLM

    def test_source_is_hybrid(self) -> None:
        regex = ApartmentSearchFilters(meta=ExtractionMeta(source="regex"))
        llm = ApartmentSearchFilters(meta=ExtractionMeta(source="llm"))
        merged = merge_extraction_results(regex, llm)
        assert merged.meta.source == "hybrid"


class TestLlmExtractorObservability:
    def test_extract_is_observed(self) -> None:
        """ApartmentLlmExtractor.extract must be @observe-decorated (span: apartment-llm-extract)."""
        assert hasattr(ApartmentLlmExtractor.extract, "__wrapped__"), (
            "ApartmentLlmExtractor.extract must be decorated with "
            "@observe(name='apartment-llm-extract')"
        )


class TestGetSystemPrompt:
    """Task 13: Tests for prompt manager integration in extraction."""

    def test_get_system_prompt_calls_get_prompt_with_correct_name(self) -> None:
        with patch("telegram_bot.services.apartment_llm_extractor.get_prompt") as mock_get_prompt:
            mock_get_prompt.return_value = "custom prompt from langfuse"
            result = _get_system_prompt()
            mock_get_prompt.assert_called_once_with(
                "apartment-extraction-system-prompt",
                fallback=EXTRACTION_SYSTEM_PROMPT,
            )
            assert result == "custom prompt from langfuse"

    def test_get_system_prompt_returns_default_when_langfuse_unavailable(self) -> None:
        with patch("telegram_bot.services.apartment_llm_extractor.get_prompt") as mock_get_prompt:
            mock_get_prompt.return_value = EXTRACTION_SYSTEM_PROMPT
            result = _get_system_prompt()
            assert "Солнечный берег" in result
            assert "Premier Fort Beach" in result

    def test_extraction_system_prompt_still_exported(self) -> None:
        """EXTRACTION_SYSTEM_PROMPT must remain importable for backward compatibility."""
        assert EXTRACTION_SYSTEM_PROMPT
        assert "Солнечный берег" in EXTRACTION_SYSTEM_PROMPT

    def test_system_prompt_forbids_null_view_tags(self) -> None:
        assert "view_tags=[]" in EXTRACTION_SYSTEM_PROMPT
        assert "Никогда не возвращай null для массивов" in EXTRACTION_SYSTEM_PROMPT
