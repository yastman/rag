"""Unit tests for LLMService."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

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

    def test_init_creates_httpx_client(self):
        """Test that httpx.AsyncClient is created with correct timeout."""
        with patch("telegram_bot.services.llm.httpx.AsyncClient") as mock_client:
            LLMService(api_key="test-key")
            mock_client.assert_called_once_with(timeout=60.0)


class TestLLMServiceGenerateAnswer:
    """Tests for LLMService.generate_answer."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance with mocked client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock(spec=httpx.AsyncClient)
        return service

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

    async def test_generate_answer_returns_response(self, service, sample_chunks):
        """Test successful answer generation."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Generated answer text"}}]
        }
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert result == "Generated answer text"
        service.client.post.assert_called_once()
        call_args = service.client.post.call_args
        assert "/chat/completions" in call_args[0][0]
        assert "Authorization" in call_args[1]["headers"]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    async def test_generate_answer_custom_system_prompt(self, service, sample_chunks):
        """Test answer generation with custom system prompt."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Custom response"}}]}
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        custom_prompt = "You are a helpful assistant."
        result = await service.generate_answer(
            "Question?", sample_chunks, system_prompt=custom_prompt
        )

        assert result == "Custom response"
        call_args = service.client.post.call_args
        messages = call_args[1]["json"]["messages"]
        assert messages[0]["content"] == custom_prompt

    async def test_generate_answer_timeout_fallback(self, service, sample_chunks):
        """Test fallback on timeout exception."""
        service.client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "Sea View Apt" in result

    async def test_generate_answer_http_error_fallback(self, service, sample_chunks):
        """Test fallback on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
        service.client.post = AsyncMock(side_effect=error)

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result

    async def test_generate_answer_empty_chunks_fallback(self, service):
        """Test fallback with empty chunks."""
        service.client.post = AsyncMock(side_effect=Exception("API error"))

        result = await service.generate_answer("What apartments?", [])

        assert "Извините, сервис временно недоступен" in result

    async def test_generate_answer_generic_exception_fallback(self, service, sample_chunks):
        """Test fallback on generic exception."""
        service.client.post = AsyncMock(side_effect=Exception("Unknown error"))

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result


class TestLLMServiceStreamAnswer:
    """Tests for LLMService.stream_answer."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance with mocked client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock(spec=httpx.AsyncClient)
        return service

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

    async def test_stream_answer_yields_chunks(self, service, sample_chunks):
        """Test that stream_answer yields content chunks."""

        # Create mock response with SSE data
        async def mock_aiter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            yield 'data: {"choices": [{"delta": {"content": " World"}}]}'
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    async def test_stream_answer_skips_empty_lines(self, service, sample_chunks):
        """Test that empty lines in SSE stream are skipped."""

        async def mock_aiter_lines():
            yield ""
            yield "   "
            yield 'data: {"choices": [{"delta": {"content": "Content"}}]}'
            yield ""
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Content"]

    async def test_stream_answer_timeout_yields_fallback(self, service, sample_chunks):
        """Test that timeout yields fallback message."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = httpx.TimeoutException("Timeout")

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_http_error_yields_fallback(self, service, sample_chunks):
        """Test that HTTP error yields fallback message."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        error = httpx.HTTPStatusError(
            "Service unavailable", request=MagicMock(), response=mock_response
        )

        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = error

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_custom_system_prompt(self, service, sample_chunks):
        """Test stream with custom system prompt."""

        async def mock_aiter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Test"}}]}'
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer(
            "Question?", sample_chunks, system_prompt="Custom prompt"
        ):
            chunks.append(chunk)

        assert chunks == ["Test"]
        call_args = service.client.stream.call_args
        messages = call_args[1]["json"]["messages"]
        assert messages[0]["content"] == "Custom prompt"

    async def test_stream_answer_skips_empty_content(self, service, sample_chunks):
        """Test that empty content in delta is skipped."""

        async def mock_aiter_lines():
            yield 'data: {"choices": [{"delta": {"role": "assistant"}}]}'  # No content
            yield 'data: {"choices": [{"delta": {"content": ""}}]}'  # Empty content
            yield 'data: {"choices": [{"delta": {"content": "Actual"}}]}'
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Actual"]

    async def test_stream_answer_handles_json_decode_error(self, service, sample_chunks):
        """Test that invalid JSON in SSE stream is skipped."""

        async def mock_aiter_lines():
            yield "data: invalid json"
            yield 'data: {"choices": [{"delta": {"content": "Valid"}}]}'
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        service.client.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Valid"]

    async def test_stream_answer_generic_exception_yields_fallback(self, service, sample_chunks):
        """Test that generic exception yields fallback message."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = Exception("Unknown error")

        service.client.stream = MagicMock(return_value=mock_context)

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
    """Tests for LLMService.generate method."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance with mocked client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock(spec=httpx.AsyncClient)
        return service

    async def test_generate_returns_content(self, service):
        """Test successful generation."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Generated text"}}]}
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        result = await service.generate("Test prompt")

        assert result == "Generated text"

    async def test_generate_uses_low_temperature(self, service):
        """Test that generate uses low temperature for deterministic output."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        await service.generate("Prompt")

        call_args = service.client.post.call_args
        assert call_args[1]["json"]["temperature"] == 0.3

    async def test_generate_custom_max_tokens(self, service):
        """Test generate with custom max_tokens."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        await service.generate("Prompt", max_tokens=500)

        call_args = service.client.post.call_args
        assert call_args[1]["json"]["max_tokens"] == 500

    async def test_generate_default_max_tokens(self, service):
        """Test generate uses default max_tokens of 200."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        await service.generate("Prompt")

        call_args = service.client.post.call_args
        assert call_args[1]["json"]["max_tokens"] == 200

    async def test_generate_raises_on_error(self, service):
        """Test that generate raises exception on API error."""
        service.client.post = AsyncMock(side_effect=Exception("API error"))

        with pytest.raises(Exception, match="API error"):
            await service.generate("Prompt")

    async def test_generate_sends_correct_message_format(self, service):
        """Test that generate sends simple user message format."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
        mock_response.raise_for_status = MagicMock()
        service.client.post = AsyncMock(return_value=mock_response)

        await service.generate("My prompt")

        call_args = service.client.post.call_args
        messages = call_args[1]["json"]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "My prompt"


class TestLLMServiceClose:
    """Tests for LLMService.close method."""

    async def test_close_calls_aclose(self):
        """Test that close method calls aclose on client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock(spec=httpx.AsyncClient)

        await service.close()

        service.client.aclose.assert_called_once()

    async def test_close_integration(self):
        """Test close with real client (integration-style)."""
        service = LLMService(api_key="test-key")

        # Should not raise
        await service.close()
