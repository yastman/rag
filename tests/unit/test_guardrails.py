"""Unit tests for guardrails features.

Tests confidence scoring, low confidence fallback, and off-topic detection.
"""

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from telegram_bot.services.llm import ConfidenceResult, LLMService, LOW_CONFIDENCE_THRESHOLD
from telegram_bot.services.query_router import (
    QueryType,
    classify_query,
    get_off_topic_response,
    is_off_topic,
)


class TestConfidenceResult:
    """Tests for ConfidenceResult dataclass."""

    def test_confidence_result_creation(self):
        """Test ConfidenceResult can be created with all fields."""
        result = ConfidenceResult(
            answer="Test answer",
            confidence=0.85,
            is_low_confidence=False,
            raw_response='{"answer": "Test answer", "confidence": 0.85}',
        )

        assert result.answer == "Test answer"
        assert result.confidence == 0.85
        assert result.is_low_confidence is False
        assert result.raw_response is not None

    def test_confidence_result_with_low_confidence(self):
        """Test ConfidenceResult with low confidence flag."""
        result = ConfidenceResult(
            answer="Uncertain answer",
            confidence=0.3,
            is_low_confidence=True,
        )

        assert result.is_low_confidence is True
        assert result.confidence < LOW_CONFIDENCE_THRESHOLD

    def test_confidence_result_without_raw_response(self):
        """Test ConfidenceResult without raw_response (optional field)."""
        result = ConfidenceResult(
            answer="Test",
            confidence=0.5,
            is_low_confidence=False,
        )

        assert result.raw_response is None


class TestConfidenceScoring:
    """Tests for confidence scoring in LLMService."""

    @pytest.fixture
    def sample_chunks(self):
        """Sample context chunks for testing."""
        return [
            {
                "text": "Apartment in Sunny Beach",
                "metadata": {"title": "Beach Apt", "price": 50000},
                "score": 0.9,
            }
        ]

    async def test_generate_answer_with_confidence(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test generate_answer returns ConfidenceResult when with_confidence=True."""
        response_json = json.dumps({"answer": "Found an apartment", "confidence": 0.85})
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Find apartments", sample_chunks, with_confidence=True
            )

        assert isinstance(result, ConfidenceResult)
        assert result.answer == "Found an apartment"
        assert result.confidence == 0.85
        assert result.is_low_confidence is False

    async def test_generate_answer_without_confidence(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test generate_answer returns string when with_confidence=False."""
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": "Plain answer"}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Find apartments", sample_chunks, with_confidence=False
            )

        assert isinstance(result, str)
        assert result == "Plain answer"

    async def test_low_confidence_detection(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test is_low_confidence is True when confidence < threshold."""
        response_json = json.dumps({"answer": "Uncertain answer", "confidence": 0.3})
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        assert result.is_low_confidence is True
        assert result.confidence < LOW_CONFIDENCE_THRESHOLD

    async def test_confidence_parsing_from_markdown_json(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test parsing confidence from JSON wrapped in markdown code blocks."""
        response = """```json
{"answer": "Markdown wrapped", "confidence": 0.75}
```"""
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        assert result.answer == "Markdown wrapped"
        assert result.confidence == 0.75

    async def test_confidence_clamped_to_valid_range(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test confidence values outside 0-1 are clamped."""
        # Test value > 1
        response_json = json.dumps({"answer": "Test", "confidence": 1.5})
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        assert result.confidence == 1.0

    async def test_negative_confidence_clamped(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test negative confidence is clamped to 0."""
        response_json = json.dumps({"answer": "Test", "confidence": -0.5})
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        assert result.confidence == 0.0


class TestConfidenceParsingEdgeCases:
    """Tests for edge cases in confidence response parsing."""

    @pytest.fixture
    def sample_chunks(self):
        return [{"text": "Test", "metadata": {}, "score": 0.9}]

    async def test_malformed_json_returns_raw_response(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test malformed JSON returns raw response with default confidence."""
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": "Not JSON at all"}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        assert result.answer == "Not JSON at all"
        assert result.confidence == 0.5  # Default on parse failure

    async def test_missing_answer_field(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test missing answer field uses raw response."""
        response_json = json.dumps({"confidence": 0.8})
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        # Should use raw response as answer
        assert result.confidence == 0.8

    async def test_missing_confidence_uses_default(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test missing confidence field uses default value."""
        response_json = json.dumps({"answer": "Answer only"})
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Query", sample_chunks, with_confidence=True
            )

        assert result.answer == "Answer only"
        assert result.confidence == 0.5  # Default when missing


class TestOffTopicDetection:
    """Tests for off-topic query detection."""

    @pytest.mark.parametrize(
        "query,expected_type",
        [
            # Programming/Tech
            ("Как написать функцию на python?", QueryType.OFF_TOPIC),
            ("What is kubernetes?", QueryType.OFF_TOPIC),
            ("Помоги с docker контейнером", QueryType.OFF_TOPIC),
            # Medical
            ("Какие симптомы гриппа?", QueryType.OFF_TOPIC),
            ("Нужен рецепт лекарства", QueryType.OFF_TOPIC),
            # Cooking
            ("Рецепт борща", QueryType.OFF_TOPIC),
            ("How to cook pasta?", QueryType.OFF_TOPIC),
            # Legal (non-property)
            ("Как подать на развод?", QueryType.OFF_TOPIC),
            # Finance (non-property)
            ("Курс биткоина сегодня", QueryType.OFF_TOPIC),
            ("Как торговать на бирже?", QueryType.OFF_TOPIC),
            # Entertainment
            ("Посоветуй хороший фильм", QueryType.OFF_TOPIC),
            ("Best video games 2024", QueryType.OFF_TOPIC),
        ],
    )
    def test_off_topic_queries_detected(self, query: str, expected_type: QueryType):
        """Test various off-topic queries are correctly classified."""
        result = classify_query(query)
        assert result == expected_type

    @pytest.mark.parametrize(
        "query,expected_type",
        [
            # Real estate queries should NOT be off-topic
            ("Квартира в Несебре до 50000 евро", QueryType.COMPLEX),
            ("Дом у моря", QueryType.COMPLEX),
            ("сколько стоит квартира", QueryType.SIMPLE),
            ("2 комнаты в Бургасе", QueryType.SIMPLE),
            # Chitchat should still work
            ("Привет", QueryType.CHITCHAT),
            ("Спасибо за помощь", QueryType.CHITCHAT),
        ],
    )
    def test_real_estate_queries_not_off_topic(self, query: str, expected_type: QueryType):
        """Test real estate queries are not classified as off-topic."""
        result = classify_query(query)
        assert result == expected_type

    def test_is_off_topic_helper(self):
        """Test is_off_topic helper function."""
        assert is_off_topic("Как написать алгоритм?") is True
        assert is_off_topic("Квартира в Варне") is False

    def test_get_off_topic_response_returns_string(self):
        """Test get_off_topic_response returns a valid response."""
        response = get_off_topic_response()

        assert isinstance(response, str)
        assert len(response) > 0
        assert "недвижимост" in response.lower()


class TestQueryTypeEnum:
    """Tests for QueryType enum."""

    def test_off_topic_enum_value(self):
        """Test OFF_TOPIC is a valid QueryType."""
        assert QueryType.OFF_TOPIC.value == "off_topic"

    def test_all_query_types_present(self):
        """Test all expected query types are defined."""
        expected_types = {"chitchat", "simple", "complex", "off_topic"}
        actual_types = {qt.value for qt in QueryType}

        assert expected_types == actual_types


class TestLowConfidenceResponse:
    """Tests for low confidence response generation."""

    def test_low_confidence_response_with_results(self):
        """Test low confidence response includes search results."""
        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Beach property",
                "metadata": {"title": "Ocean View", "price": 60000, "city": "Varna", "rooms": 2},
                "score": 0.8,
            }
        ]

        response = service.get_low_confidence_response("Query", chunks, 0.4)

        assert "Не уверен" in response
        assert "40%" in response
        assert "Ocean View" in response
        assert "Varna" in response

    def test_low_confidence_response_empty_context(self):
        """Test low confidence response with no search results."""
        service = LLMService(api_key="test-key")

        response = service.get_low_confidence_response("Query", [], 0.2)

        assert "Не уверен" in response
        assert "20%" in response
        assert "не нашёл релевантной информации" in response

    def test_low_confidence_threshold_value(self):
        """Test LOW_CONFIDENCE_THRESHOLD has correct value."""
        assert LOW_CONFIDENCE_THRESHOLD == 0.5


class TestGuardrailsIntegration:
    """Integration tests for guardrails features."""

    @pytest.fixture
    def sample_chunks(self):
        return [
            {
                "text": "Apartment data",
                "metadata": {"title": "Test Apt", "price": 45000, "city": "Sofia"},
                "score": 0.9,
            }
        ]

    async def test_high_confidence_answer_returned_as_is(
        self, httpx_mock: HTTPXMock, sample_chunks
    ):
        """Test high confidence answers are returned without modification."""
        response_json = json.dumps(
            {"answer": "Great apartment in Sofia for 45000€", "confidence": 0.9}
        )
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": response_json}}]}
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Find apartments in Sofia", sample_chunks, with_confidence=True
            )

        assert result.confidence >= LOW_CONFIDENCE_THRESHOLD
        assert result.is_low_confidence is False
        assert "Sofia" in result.answer

    async def test_off_topic_query_flow(self):
        """Test complete flow for off-topic queries."""
        query = "Как приготовить пиццу?"

        # Should be classified as off-topic
        query_type = classify_query(query)
        assert query_type == QueryType.OFF_TOPIC

        # Should get appropriate response
        response = get_off_topic_response()
        assert "недвижимост" in response.lower()
