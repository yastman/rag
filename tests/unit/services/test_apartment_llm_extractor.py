"""Tests for the native structured-output apartment filter extractor (#3224)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from litellm.exceptions import APIConnectionError
from pydantic import ValidationError

from src.models.apartment import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)
from src.runtime.llm import LiteLlmClient, create_llm_client
from telegram_bot.services.apartment.apartment_llm_extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    ApartmentLlmExtractor,
    _get_system_prompt,
    merge_extraction_results,
)


@pytest.fixture
def mock_llm_result() -> ApartmentSearchFilters:
    return ApartmentSearchFilters(
        hard=HardFilters(city="Солнечный берег", rooms=2, max_price_eur=100000),
        soft=SoftPreferences(near_sea=True),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )


def _mock_client(result: ApartmentSearchFilters | Exception) -> LiteLlmClient:
    """Build a LiteLlmClient-spec'd mock whose structured() returns/raises ``result``."""
    client = AsyncMock(spec=LiteLlmClient)
    if isinstance(result, Exception):
        client.structured = AsyncMock(side_effect=result)
    else:
        client.structured = AsyncMock(return_value=result)
    return cast(LiteLlmClient, client)


class _JsonContentRouter:
    """Fake SDK router whose acompletion returns one object-valued message."""

    def __init__(self, content: object) -> None:
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        self.acompletion = AsyncMock(return_value=SimpleNamespace(choices=[choice]))


def _make_extractor(client: LiteLlmClient) -> ApartmentLlmExtractor:
    return ApartmentLlmExtractor(llm=client, model="gpt-4o-mini")


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
        extractor = _make_extractor(_mock_client(mock_llm_result))

        result = await extractor.extract(query="просторная у моря")
        assert result.meta.source == "llm"

    async def test_extract_partial_sets_source_hybrid(
        self, mock_llm_result: ApartmentSearchFilters
    ) -> None:
        extractor = _make_extractor(_mock_client(mock_llm_result))

        partial = HardFilters(rooms=2)
        result = await extractor.extract(query="солнечный берег", partial_filters=partial)
        assert result.meta.source == "hybrid"

    async def test_calls_native_boundary_with_schema_and_observation_name(
        self, mock_llm_result: ApartmentSearchFilters
    ) -> None:
        """Gap-fill must go through LiteLlmClient.structured with the schema model."""
        client = _mock_client(mock_llm_result)
        extractor = _make_extractor(client)

        await extractor.extract(query="двушка у моря")

        kwargs = client.structured.await_args.kwargs
        assert kwargs["response_model"] is ApartmentSearchFilters
        assert kwargs["observation_name"] == "apartment-gap-fill"
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["messages"][1] == {"role": "user", "content": "двушка у моря"}

    async def test_partial_filters_forwarded_as_gap_fill_context(
        self, mock_llm_result: ApartmentSearchFilters
    ) -> None:
        client = _mock_client(mock_llm_result)
        extractor = _make_extractor(client)

        await extractor.extract(
            query="двушка", partial_filters=HardFilters(rooms=2, max_price_eur=100000)
        )

        system_content = client.structured.await_args.kwargs["messages"][0]["content"]
        assert "rooms" in system_content
        assert "max_price_eur" in system_content

    async def test_invalid_city_cleared(self) -> None:
        # Bypass Literal validation to emulate malformed LLM output.
        bad_result = ApartmentSearchFilters.model_construct(
            hard=HardFilters.model_construct(city="Бургас", rooms=2),
            meta=ExtractionMeta(source="llm"),
        )
        extractor = _make_extractor(_mock_client(bad_result))

        result = await extractor.extract(query="квартира в бургасе")
        assert result.hard.city is None  # очищено post-validation

    async def test_valid_city_preserved(self, mock_llm_result: ApartmentSearchFilters) -> None:
        extractor = _make_extractor(_mock_client(mock_llm_result))

        result = await extractor.extract(query="солнечный берег двушка")
        assert result.hard.city == "Солнечный берег"

    async def test_extract_coerces_null_view_tags_from_llm(self) -> None:
        bad_result = ApartmentSearchFilters.model_construct(
            hard=HardFilters.model_construct(view_tags=None),
            meta=ExtractionMeta(source="llm"),
        )
        extractor = _make_extractor(_mock_client(bad_result))

        result = await extractor.extract(query="квартира без уточнения вида")
        assert result.hard.view_tags == []


class TestNativeStructuredRoundTrip:
    """The extractor runs against a real LiteLlmClient over a fake SDK router."""

    async def test_json_response_validates_into_filters(self) -> None:
        router = _JsonContentRouter(
            {
                "hard": {"city": "Солнечный берег", "rooms": 2, "max_price_eur": 100000},
                "soft": {"near_sea": True},
                "meta": {"source": "llm", "confidence": "HIGH"},
            }
        )
        extractor = _make_extractor(
            create_llm_client(model="gpt-4o-mini", router=router, timeout=5)
        )

        result = await extractor.extract(query="двушка у моря до 100к")

        assert isinstance(result, ApartmentSearchFilters)
        assert result.hard.city == "Солнечный берег"
        assert result.hard.rooms == 2
        assert result.hard.max_price_eur == 100000
        assert result.soft.near_sea is True
        assert result.meta.source == "llm"
        # The strict JSON-schema response_format was derived from the model.
        response_format = router.acompletion.await_args.kwargs["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == "ApartmentSearchFilters"
        assert response_format["json_schema"]["strict"] is True

    async def test_schema_invalid_output_raises_validation_error(self) -> None:
        router = _JsonContentRouter({"hard": {"rooms": "not-a-number"}})
        extractor = _make_extractor(
            create_llm_client(model="gpt-4o-mini", router=router, timeout=5)
        )

        with pytest.raises(ValidationError):
            await extractor.extract(query="двушка")

    async def test_provider_connection_error_propagates(self) -> None:
        """Provider failure propagates unchanged to the pipeline's regex-only fallback."""

        class _DownRouter:
            async def acompletion(self, **kwargs: object) -> object:
                raise APIConnectionError(
                    message="provider unreachable",
                    llm_provider="openai",
                    model="gpt-4o-mini",
                )

        extractor = _make_extractor(
            create_llm_client(model="gpt-4o-mini", router=_DownRouter(), timeout=5)
        )
        with pytest.raises(APIConnectionError):
            await extractor.extract(query="двушка")


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


class TestGetSystemPrompt:
    """Task 13: Tests for prompt manager integration in extraction."""

    def test_get_system_prompt_calls_get_prompt_with_correct_name(self) -> None:
        with patch(
            "telegram_bot.services.apartment.apartment_llm_extractor.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "custom prompt from langfuse"
            result = _get_system_prompt()
            mock_get_prompt.assert_called_once_with(
                "apartment-extraction-system-prompt",
                fallback=EXTRACTION_SYSTEM_PROMPT,
            )
            assert result == "custom prompt from langfuse"

    def test_get_system_prompt_returns_default_when_langfuse_unavailable(self) -> None:
        with patch(
            "telegram_bot.services.apartment.apartment_llm_extractor.get_prompt"
        ) as mock_get_prompt:
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
