"""Chaos tests for LLM fallback chain.

Tests verify graceful degradation when LLM services fail.
"""

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from telegram_bot.services.llm import LOW_CONFIDENCE_THRESHOLD, ConfidenceResult, LLMService


pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)


class TestLLMTimeout:
    """Tests for LLM timeout handling."""

    async def test_llm_timeout_returns_fallback_answer(self, httpx_mock: HTTPXMock):
        """Verify fallback answer returned on LLM timeout."""
        httpx_mock.add_exception(httpx.TimeoutException("LLM request timed out"))

        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Beach apartment",
                "metadata": {"title": "Sea View", "price": 50000, "city": "Nesebar"},
                "score": 0.9,
            }
        ]

        result = await service.generate_answer("What apartments?", chunks)

        assert "временно недоступен" in result
        assert "Sea View" in result

    async def test_llm_timeout_with_confidence_returns_low_confidence(self, httpx_mock: HTTPXMock):
        """Verify low confidence returned on LLM timeout with confidence mode."""
        httpx_mock.add_exception(httpx.TimeoutException("LLM request timed out"))

        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Beach apartment",
                "metadata": {"title": "Sea View", "price": 50000},
                "score": 0.9,
            }
        ]

        result = await service.generate_answer("What apartments?", chunks, with_confidence=True)

        assert isinstance(result, ConfidenceResult)
        assert result.confidence == 0.0
        assert result.is_low_confidence is True


class TestLLMHTTPErrors:
    """Tests for LLM HTTP error handling."""

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504, 429])
    async def test_llm_server_error_returns_fallback(self, httpx_mock: HTTPXMock, status_code: int):
        """Verify fallback on various server errors."""
        httpx_mock.add_response(status_code=status_code)

        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Apartment details",
                "metadata": {"title": "Downtown Flat", "price": 40000},
                "score": 0.85,
            }
        ]

        result = await service.generate_answer("Find apartments", chunks)

        assert "временно недоступен" in result

    @pytest.mark.parametrize(
        ("status_code", "error_json"),
        [
            pytest.param(429, {"error": {"message": "Rate limit exceeded"}}, id="rate_limit"),
            pytest.param(401, {"error": {"message": "Invalid API key"}}, id="auth_error"),
        ],
    )
    async def test_llm_error_with_json_body_fallback(
        self, httpx_mock: HTTPXMock, status_code, error_json
    ):
        """Verify graceful handling of HTTP errors with JSON body."""
        httpx_mock.add_response(status_code=status_code, json=error_json)

        service = LLMService(api_key="test-key")
        result = await service.generate_answer("Query", [])

        assert "временно недоступен" in result


class TestLLMResponseParsing:
    """Tests for LLM response parsing failures."""

    async def test_malformed_json_response_handled(self, httpx_mock: HTTPXMock):
        """Verify handling of malformed JSON in LLM response."""
        httpx_mock.add_response(json={"choices": [{"message": {"content": "not json response"}}]})

        service = LLMService(api_key="test-key")

        result = await service.generate_answer(
            "Query",
            [{"text": "context", "metadata": {}, "score": 0.9}],
            with_confidence=True,
        )

        # Should return result with default confidence (parsing failed)
        assert isinstance(result, ConfidenceResult)
        assert result.answer == "not json response"
        assert result.confidence == 0.5  # Default on parse failure

    async def test_missing_confidence_field_handled(self, httpx_mock: HTTPXMock):
        """Verify handling when confidence field is missing."""
        httpx_mock.add_response(
            json={
                "choices": [
                    {"message": {"content": json.dumps({"answer": "Response without confidence"})}}
                ]
            }
        )

        service = LLMService(api_key="test-key")

        result = await service.generate_answer(
            "Query",
            [{"text": "context", "metadata": {}, "score": 0.9}],
            with_confidence=True,
        )

        assert isinstance(result, ConfidenceResult)
        assert result.confidence == 0.5  # Default when missing

    async def test_invalid_confidence_value_clamped(self, httpx_mock: HTTPXMock):
        """Verify invalid confidence values are clamped to valid range."""
        httpx_mock.add_response(
            json={
                "choices": [
                    {"message": {"content": json.dumps({"answer": "Test", "confidence": 1.5})}}
                ]
            }
        )

        service = LLMService(api_key="test-key")

        result = await service.generate_answer(
            "Query",
            [{"text": "context", "metadata": {}, "score": 0.9}],
            with_confidence=True,
        )

        assert result.confidence == 1.0  # Clamped to max


class TestLLMFallbackChain:
    """Tests for LLM fallback chain behavior."""

    async def test_empty_context_fallback_message(self, httpx_mock: HTTPXMock):
        """Verify appropriate fallback when context is empty and LLM fails."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        service = LLMService(api_key="test-key")

        result = await service.generate_answer("Query", [])

        assert "сервис временно недоступен" in result.lower()
        assert "повторить запрос" in result.lower()

    async def test_fallback_includes_search_results(self, httpx_mock: HTTPXMock):
        """Verify fallback includes available search results."""
        httpx_mock.add_exception(Exception("LLM unavailable"))

        service = LLMService(api_key="test-key")

        chunks = [
            {"text": "Apt 1", "metadata": {"title": "First", "price": 30000}, "score": 0.9},
            {"text": "Apt 2", "metadata": {"title": "Second", "price": 40000}, "score": 0.8},
            {"text": "Apt 3", "metadata": {"title": "Third", "price": 50000}, "score": 0.7},
        ]

        result = await service.generate_answer("Query", chunks)

        # Should show first 3 results
        assert "First" in result
        assert "Second" in result
        assert "Third" in result
        assert "30,000€" in result or "30000€" in result


class TestLLMStreamingFallback:
    """Tests for LLM streaming fallback."""

    @pytest.mark.parametrize(
        ("setup_mock", "chunks"),
        [
            pytest.param(
                "timeout",
                [{"text": "Data", "metadata": {"title": "Test"}, "score": 0.9}],
                id="timeout",
            ),
            pytest.param("http_500", [], id="http_error"),
        ],
    )
    async def test_streaming_error_yields_fallback(
        self, httpx_mock: HTTPXMock, setup_mock, chunks
    ):
        """Verify streaming yields fallback on error."""
        if setup_mock == "timeout":
            httpx_mock.add_exception(httpx.TimeoutException("Stream timeout"))
        else:
            httpx_mock.add_response(status_code=500)

        service = LLMService(api_key="test-key")

        collected = []
        async for chunk in service.stream_answer("Query", chunks):
            collected.append(chunk)

        full_response = "".join(collected)
        assert "временно недоступен" in full_response


class TestLowConfidenceFallback:
    """Tests for low confidence response generation."""

    def test_low_confidence_response_format(self):
        """Verify low confidence response format is correct."""
        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Data",
                "metadata": {"title": "Beach Apt", "price": 50000, "city": "Varna"},
                "score": 0.8,
            }
        ]

        response = service.get_low_confidence_response("Query", chunks, 0.35)

        assert "Не уверен" in response
        assert "35%" in response
        assert "Beach Apt" in response
        assert "50,000€" in response or "50000€" in response
        assert "Varna" in response

    def test_low_confidence_empty_context(self):
        """Verify low confidence response with empty context."""
        service = LLMService(api_key="test-key")

        response = service.get_low_confidence_response("Query", [], 0.2)

        assert "Не уверен" in response
        assert "20%" in response
        assert "не нашёл релевантной информации" in response

    def test_confidence_threshold_constant(self):
        """Verify LOW_CONFIDENCE_THRESHOLD is defined correctly."""
        assert LOW_CONFIDENCE_THRESHOLD == 0.3
        assert 0.0 < LOW_CONFIDENCE_THRESHOLD < 1.0
