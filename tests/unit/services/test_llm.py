"""Unit tests for LLMService.

Uses pytest-httpx for robust HTTP mocking (2026 best practice).
No manual AsyncMock hacks - pytest-httpx hooks into httpx transport layer.
"""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pytest_httpx import HTTPXMock, IteratorStream

# Import directly from the module to avoid importing voyage/torch via __init__.py
from telegram_bot.services.llm import LLMService


class TestLLMServiceInit:
    """Tests for LLMService.__init__."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        service = LLMService(api_key="test-key")

        assert service.api_key == "test-key"
        assert service.base_url == "https://api.openai.com/v1"
        assert service.model == "gpt-4o-mini"
        assert isinstance(service.client, httpx.AsyncClient)
        assert service._owns_client is True

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        service = LLMService(
            api_key="custom-key",
            base_url="https://custom.api.com/v1/",
            model="custom-model",
        )

        assert service.api_key == "custom-key"
        assert service.base_url == "https://custom.api.com/v1"  # Trailing slash stripped
        assert service.model == "custom-model"

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base_url."""
        service = LLMService(
            api_key="test-key",
            base_url="https://api.example.com///",
        )

        # rstrip("/") removes ALL trailing slashes
        assert service.base_url == "https://api.example.com"

    def test_init_with_injected_client(self):
        """Test initialization with injected client (dependency injection)."""
        custom_client = httpx.AsyncClient(timeout=30.0)
        service = LLMService(api_key="test-key", client=custom_client)

        assert service.client is custom_client
        assert service._owns_client is False

    def test_init_creates_httpx_client_when_not_injected(self):
        """Test that httpx.AsyncClient is created when not injected."""
        service = LLMService(api_key="test-key")

        assert isinstance(service.client, httpx.AsyncClient)
        assert service._owns_client is True


class TestLLMServiceGenerateAnswer:
    """Tests for LLMService.generate_answer using pytest-httpx."""

    @pytest.fixture
    def sample_chunks(self):
        """Sample context chunks for testing."""
        return [
            {
                "text": "Apartment near beach",
                "metadata": {"title": "Sea View Apt", "city": "Sunny Beach", "price": 50000},
                "score": 0.95,
            },
            {
                "text": "Studio in center",
                "metadata": {"title": "Central Studio", "city": "Sofia", "price": 35000},
                "score": 0.85,
            },
        ]

    async def test_generate_answer_returns_response(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test successful answer generation."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Generated answer text"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer("What apartments?", sample_chunks)

        assert result == "Generated answer text"

    async def test_generate_answer_custom_system_prompt(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test answer generation with custom system prompt."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Custom response"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer(
                "Question?", sample_chunks, system_prompt="Custom prompt"
            )

        assert result == "Custom response"
        # Verify request was sent with custom prompt
        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["messages"][0]["content"] == "Custom prompt"

    async def test_generate_answer_timeout_fallback(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test fallback on timeout exception."""
        httpx_mock.add_exception(httpx.TimeoutException("Timeout"))

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "Sea View Apt" in result

    async def test_generate_answer_http_error_fallback(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test fallback on HTTP error."""
        httpx_mock.add_response(status_code=500)

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result

    async def test_generate_answer_empty_chunks_fallback(self, httpx_mock: HTTPXMock):
        """Test fallback with empty chunks."""
        httpx_mock.add_exception(Exception("API error"))

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate_answer("What apartments?", [])

        assert "Извините, сервис временно недоступен" in result


class TestLLMServiceStreamAnswer:
    """Tests for LLMService.stream_answer using pytest-httpx with IteratorStream."""

    @pytest.fixture
    def sample_chunks(self):
        """Sample context chunks for testing."""
        return [
            {
                "text": "Apartment near beach",
                "metadata": {"title": "Sea View Apt", "city": "Sunny Beach", "price": 50000},
                "score": 0.95,
            },
        ]

    async def test_stream_answer_yields_chunks(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test that stream_answer yields content chunks."""
        # SSE format with proper line endings
        sse_chunks = [
            b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": " World"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            stream=IteratorStream(sse_chunks),
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    async def test_stream_answer_skips_empty_lines(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test that empty lines in SSE stream are skipped."""
        sse_chunks = [
            b"\n\n",
            b"   \n\n",
            b'data: {"choices": [{"delta": {"content": "Content"}}]}\n\n',
            b"\n\n",
            b"data: [DONE]\n\n",
        ]

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            stream=IteratorStream(sse_chunks),
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert chunks == ["Content"]

    async def test_stream_answer_timeout_yields_fallback(
        self, httpx_mock: HTTPXMock, sample_chunks
    ):
        """Test that timeout yields fallback message."""
        httpx_mock.add_exception(httpx.TimeoutException("Timeout"))

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_http_error_yields_fallback(
        self, httpx_mock: HTTPXMock, sample_chunks
    ):
        """Test that HTTP error yields fallback message."""
        httpx_mock.add_response(status_code=503)

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_custom_system_prompt(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test stream with custom system prompt."""
        sse_chunks = [
            b'data: {"choices": [{"delta": {"content": "Test"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            stream=IteratorStream(sse_chunks),
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer(
                "Question?", sample_chunks, system_prompt="Custom prompt"
            ):
                chunks.append(chunk)

        assert chunks == ["Test"]
        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["messages"][0]["content"] == "Custom prompt"

    async def test_stream_answer_skips_empty_content(self, httpx_mock: HTTPXMock, sample_chunks):
        """Test that empty content in delta is skipped."""
        sse_chunks = [
            b'data: {"choices": [{"delta": {"role": "assistant"}}]}\n\n',  # No content
            b'data: {"choices": [{"delta": {"content": ""}}]}\n\n',  # Empty content
            b'data: {"choices": [{"delta": {"content": "Actual"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            stream=IteratorStream(sse_chunks),
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert chunks == ["Actual"]

    async def test_stream_answer_handles_json_decode_error(
        self, httpx_mock: HTTPXMock, sample_chunks
    ):
        """Test that invalid JSON in SSE stream is skipped."""
        sse_chunks = [
            b"data: invalid json\n\n",
            b'data: {"choices": [{"delta": {"content": "Valid"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            stream=IteratorStream(sse_chunks),
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert chunks == ["Valid"]

    async def test_stream_answer_generic_exception_yields_fallback(
        self, httpx_mock: HTTPXMock, sample_chunks
    ):
        """Test that generic exception yields fallback message."""
        httpx_mock.add_exception(Exception("Unknown error"))

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            chunks = []
            async for chunk in service.stream_answer("Question?", sample_chunks):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]


class TestLLMServiceFormatContext:
    """Tests for LLMService._format_context."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance."""
        return LLMService(api_key="test-key")

    def test_format_context_empty_chunks(self, service):
        """Test formatting with empty chunks list."""
        result = service._format_context([])

        assert result == "Релевантной информации не найдено."

    def test_format_context_single_chunk(self, service):
        """Test formatting with single chunk."""
        chunks = [{"text": "Property description", "score": 0.92}]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "релевантность: 0.92" in result
        assert "Property description" in result

    def test_format_context_with_metadata(self, service):
        """Test formatting with full metadata."""
        chunks = [
            {
                "text": "Nice apartment",
                "metadata": {"title": "Beach Apt", "city": "Varna", "price": 75000},
                "score": 0.88,
            }
        ]

        result = service._format_context(chunks)

        assert "Название: Beach Apt" in result
        assert "Город: Varna" in result
        assert "Цена: 75,000" in result
        assert "Nice apartment" in result

    def test_format_context_multiple_chunks(self, service):
        """Test formatting with multiple chunks."""
        chunks = [
            {"text": "First property", "score": 0.95},
            {"text": "Second property", "score": 0.85},
            {"text": "Third property", "score": 0.75},
        ]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "[Объект 2]" in result
        assert "[Объект 3]" in result
        assert "First property" in result
        assert "Second property" in result
        assert "Third property" in result
        # Check separator
        assert "---" in result

    def test_format_context_partial_metadata(self, service):
        """Test formatting with partial metadata (only title)."""
        chunks = [
            {
                "text": "Property text",
                "metadata": {"title": "Only Title"},
                "score": 0.80,
            }
        ]

        result = service._format_context(chunks)

        assert "Название: Only Title" in result
        assert "Город:" not in result
        assert "Цена:" not in result

    def test_format_context_no_metadata(self, service):
        """Test formatting without metadata dict."""
        chunks = [{"text": "Just text", "score": 0.70}]

        result = service._format_context(chunks)

        assert "Just text" in result
        assert "Название:" not in result
        assert "Город:" not in result
        assert "Цена:" not in result

    def test_format_context_missing_score(self, service):
        """Test formatting when score is missing (defaults to 0)."""
        chunks = [{"text": "No score", "metadata": {}}]

        result = service._format_context(chunks)

        assert "релевантность: 0.00" in result


class TestLLMServiceGetFallbackAnswer:
    """Tests for LLMService._get_fallback_answer."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance."""
        return LLMService(api_key="test-key")

    def test_get_fallback_answer_empty_chunks(self, service):
        """Test fallback with empty chunks."""
        result = service._get_fallback_answer("Question?", [])

        assert "Извините, сервис временно недоступен" in result
        assert "Попробуйте повторить запрос позже" in result

    def test_get_fallback_answer_formats_first_3_chunks(self, service):
        """Test that only first 3 chunks are formatted."""
        chunks = [
            {"text": "1", "metadata": {"title": "First"}},
            {"text": "2", "metadata": {"title": "Second"}},
            {"text": "3", "metadata": {"title": "Third"}},
            {"text": "4", "metadata": {"title": "Fourth"}},
            {"text": "5", "metadata": {"title": "Fifth"}},
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "1. First" in result
        assert "2. Second" in result
        assert "3. Third" in result
        assert "Fourth" not in result
        assert "Fifth" not in result

    def test_get_fallback_answer_handles_non_numeric_price(self, service):
        """Test fallback handles non-numeric price values."""
        chunks = [
            {
                "text": "Property",
                "metadata": {"title": "Test", "price": "negotiable"},
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Цена: negotiable" in result

    def test_get_fallback_answer_numeric_price(self, service):
        """Test fallback formats numeric price with separator."""
        chunks = [
            {
                "text": "Property",
                "metadata": {"title": "Test", "price": 125000},
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Цена: 125,000" in result

    def test_get_fallback_answer_all_metadata_fields(self, service):
        """Test fallback includes all metadata fields."""
        chunks = [
            {
                "text": "Description",
                "metadata": {
                    "title": "Luxury Apt",
                    "price": 200000,
                    "city": "Burgas",
                    "rooms": 3,
                },
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Luxury Apt" in result
        assert "Цена: 200,000" in result
        assert "Город: Burgas" in result
        assert "Комнат: 3" in result

    def test_get_fallback_answer_partial_metadata(self, service):
        """Test fallback with partial metadata."""
        chunks = [
            {
                "text": "Description",
                "metadata": {"city": "Sofia"},
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Город: Sofia" in result
        # Should start with "1. " even without title
        assert "1. " in result

    def test_get_fallback_answer_no_metadata(self, service):
        """Test fallback with chunk having no metadata."""
        chunks = [{"text": "Just description"}]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "1. " in result


class TestLLMServiceGenerate:
    """Tests for LLMService.generate method using pytest-httpx."""

    async def test_generate_returns_content(self, httpx_mock: HTTPXMock):
        """Test successful generation."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Generated text"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            result = await service.generate("Test prompt")

        assert result == "Generated text"

    async def test_generate_uses_low_temperature(self, httpx_mock: HTTPXMock):
        """Test that generate uses low temperature for deterministic output."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Response"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            await service.generate("Prompt")

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["temperature"] == 0.3

    async def test_generate_custom_max_tokens(self, httpx_mock: HTTPXMock):
        """Test generate with custom max_tokens."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Response"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            await service.generate("Prompt", max_tokens=500)

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["max_tokens"] == 500

    async def test_generate_default_max_tokens(self, httpx_mock: HTTPXMock):
        """Test generate uses default max_tokens of 200."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Response"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            await service.generate("Prompt")

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["max_tokens"] == 200

    async def test_generate_raises_on_error(self, httpx_mock: HTTPXMock):
        """Test that generate raises exception on API error."""
        httpx_mock.add_exception(Exception("API error"))

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            with pytest.raises(Exception, match="API error"):
                await service.generate("Prompt")

    async def test_generate_sends_correct_message_format(self, httpx_mock: HTTPXMock):
        """Test that generate sends simple user message format."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            json={"choices": [{"message": {"content": "Response"}}]},
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(api_key="test-key", client=client)
            await service.generate("My prompt")

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        messages = body["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "My prompt"


class TestLLMServiceClose:
    """Tests for LLMService.close method."""

    async def test_close_calls_aclose_when_owns_client(self):
        """Test that close method calls aclose when service owns the client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock(spec=httpx.AsyncClient)

        await service.close()

        service.client.aclose.assert_called_once()

    async def test_close_does_not_close_injected_client(self):
        """Test that close does not close an injected client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        service = LLMService(api_key="test-key", client=mock_client)

        await service.close()

        mock_client.aclose.assert_not_called()

    async def test_close_integration(self):
        """Test close with real client (integration-style)."""
        service = LLMService(api_key="test-key")

        # Should not raise
        await service.close()
