"""Unit tests for guardrails features.

Tests confidence scoring and low confidence fallback in LLMService.
Off-topic detection is now handled by classify_node in the LangGraph pipeline.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.llm import LOW_CONFIDENCE_THRESHOLD, ConfidenceResult, LLMService


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


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
            confidence=0.2,
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

    async def test_generate_answer_with_confidence(self, sample_chunks):
        """Test generate_answer returns ConfidenceResult when with_confidence=True."""
        response_json = json.dumps({"answer": "Found an apartment", "confidence": 0.85})
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer(
            "Find apartments", sample_chunks, with_confidence=True
        )

        assert isinstance(result, ConfidenceResult)
        assert result.answer == "Found an apartment"
        assert result.confidence == 0.85
        assert result.is_low_confidence is False

    async def test_generate_answer_without_confidence(self, sample_chunks):
        """Test generate_answer returns string when with_confidence=False."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Plain answer")
        )

        result = await service.generate_answer(
            "Find apartments", sample_chunks, with_confidence=False
        )

        assert isinstance(result, str)
        assert result == "Plain answer"

    async def test_low_confidence_detection(self, sample_chunks):
        """Test is_low_confidence is True when confidence < threshold."""
        response_json = json.dumps({"answer": "Uncertain answer", "confidence": 0.2})
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        assert result.is_low_confidence is True
        assert result.confidence < LOW_CONFIDENCE_THRESHOLD

    async def test_confidence_parsing_from_markdown_json(self, sample_chunks):
        """Test parsing confidence from JSON wrapped in markdown code blocks."""
        response = """```json
{"answer": "Markdown wrapped", "confidence": 0.75}
```"""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion(response))

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        assert result.answer == "Markdown wrapped"
        assert result.confidence == 0.75

    async def test_confidence_clamped_to_valid_range(self, sample_chunks):
        """Test confidence values outside 0-1 are clamped."""
        response_json = json.dumps({"answer": "Test", "confidence": 1.5})
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        assert result.confidence == 1.0

    async def test_negative_confidence_clamped(self, sample_chunks):
        """Test negative confidence is clamped to 0."""
        response_json = json.dumps({"answer": "Test", "confidence": -0.5})
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        assert result.confidence == 0.0


class TestConfidenceParsingEdgeCases:
    """Tests for edge cases in confidence response parsing."""

    @pytest.fixture
    def sample_chunks(self):
        return [{"text": "Test", "metadata": {}, "score": 0.9}]

    async def test_malformed_json_returns_raw_response(self, sample_chunks):
        """Test malformed JSON returns raw response with default confidence."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Not JSON at all")
        )

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        assert result.answer == "Not JSON at all"
        assert result.confidence == 0.5  # Default on parse failure

    async def test_missing_answer_field(self, sample_chunks):
        """Test missing answer field uses raw response."""
        response_json = json.dumps({"confidence": 0.8})
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        # Should use raw response as answer
        assert result.confidence == 0.8

    async def test_missing_confidence_uses_default(self, sample_chunks):
        """Test missing confidence field uses default value."""
        response_json = json.dumps({"answer": "Answer only"})
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer("Query", sample_chunks, with_confidence=True)

        assert result.answer == "Answer only"
        assert result.confidence == 0.5  # Default when missing


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
        assert LOW_CONFIDENCE_THRESHOLD == 0.3


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

    async def test_high_confidence_answer_returned_as_is(self, sample_chunks):
        """Test high confidence answers are returned without modification."""
        response_json = json.dumps(
            {"answer": "Great apartment in Sofia for 45000€", "confidence": 0.9}
        )
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(response_json)
        )

        result = await service.generate_answer(
            "Find apartments in Sofia", sample_chunks, with_confidence=True
        )

        assert result.confidence >= LOW_CONFIDENCE_THRESHOLD
        assert result.is_low_confidence is False
        assert "Sofia" in result.answer
