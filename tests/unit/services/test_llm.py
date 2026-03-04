"""Unit tests for LLMService.

Uses AsyncMock for OpenAI SDK client mocking.
"""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.llm import LLMService


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


class TestLLMServiceInit:
    """Tests for LLMService.__init__."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        service = LLMService(api_key="test-key")

        assert service.api_key == "test-key"
        assert service.base_url == "https://api.openai.com/v1"
        assert service.model == "gpt-4o-mini"
        assert isinstance(service.client, openai.AsyncOpenAI)

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

    def test_init_creates_openai_client(self):
        """Test that AsyncOpenAI client is created."""
        service = LLMService(api_key="test-key")

        assert isinstance(service.client, openai.AsyncOpenAI)


def test_format_context_no_raw_score():
    """_format_context must NOT expose raw RRF scores to LLM."""
    service = LLMService(api_key="test-key")

    chunks = [
        {"text": "ВНЖ по работе", "score": 0.0167, "metadata": {"title": "Виды ВНЖ"}},
        {"text": "ВНЖ пенсионеры", "score": 0.0161, "metadata": {}},
    ]
    result = service._format_context(chunks)
    # Must NOT contain raw RRF scores like "0.02" or "0.017"
    assert "0.02" not in result
    assert "0.017" not in result
    # Must contain object markers
    assert "[Объект 1]" in result
    assert "[Объект 2]" in result


class TestLLMServiceGenerateAnswer:
    """Tests for LLMService.generate_answer."""

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

    async def test_generate_answer_returns_response(self, sample_chunks):
        """Test successful answer generation."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Generated answer text")
        )

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert result == "Generated answer text"

    async def test_generate_answer_custom_system_prompt(self, sample_chunks):
        """Test answer generation with custom system prompt."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Custom response")
        )

        result = await service.generate_answer(
            "Question?", sample_chunks, system_prompt="Custom prompt"
        )

        assert result == "Custom response"
        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["messages"][0]["content"] == "Custom prompt"

    async def test_generate_answer_timeout_fallback(self, sample_chunks):
        """Test fallback on timeout exception."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "Sea View Apt" in result

    async def test_generate_answer_connection_error_fallback(self, sample_chunks):
        """Test fallback on connection error."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result

    async def test_generate_answer_empty_chunks_fallback(self):
        """Test fallback with empty chunks."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        result = await service.generate_answer("What apartments?", [])

        assert "Извините, сервис временно недоступен" in result


class TestLLMServiceStreamAnswer:
    """Tests for LLMService.stream_answer."""

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

    async def test_stream_answer_yields_chunks(self, sample_chunks):
        """Test that stream_answer yields content chunks."""
        service = LLMService(api_key="test-key")

        # Mock streaming response as async iterator
        chunk1 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="Hello"))])
        chunk2 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=" World"))])

        async def mock_stream():
            for c in [chunk1, chunk2]:
                yield c

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    async def test_stream_answer_skips_usage_chunks(self, sample_chunks):
        """Test that usage chunks are skipped."""
        service = LLMService(api_key="test-key")

        content_chunk = MagicMock(
            usage=None, choices=[MagicMock(delta=MagicMock(content="Content"))]
        )
        usage_chunk = MagicMock(usage=MagicMock(total_tokens=100), choices=[])

        async def mock_stream():
            for c in [content_chunk, usage_chunk]:
                yield c

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Content"]

    async def test_stream_answer_timeout_yields_fallback(self, sample_chunks):
        """Test that timeout yields fallback message."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_generic_exception_yields_fallback(self, sample_chunks):
        """Test that generic exception yields fallback message."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("Unknown error"))

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_skips_empty_content(self, sample_chunks):
        """Test that empty content in delta is skipped."""
        service = LLMService(api_key="test-key")

        chunk_empty = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=""))])
        chunk_none = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=None))])
        chunk_actual = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="Actual"))])

        async def mock_stream():
            for c in [chunk_empty, chunk_none, chunk_actual]:
                yield c

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Actual"]


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
        assert "релевантность" not in result
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

    def test_format_context_missing_score(self, service):
        """Test formatting when score is missing (defaults to 0)."""
        chunks = [{"text": "No score", "metadata": {}}]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "релевантность" not in result


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
        assert "1. " in result

    def test_get_fallback_answer_no_metadata(self, service):
        """Test fallback with chunk having no metadata."""
        chunks = [{"text": "Just description"}]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "1. " in result


class TestLLMServiceGenerate:
    """Tests for LLMService.generate method."""

    async def test_generate_returns_content(self):
        """Test successful generation."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Generated text")
        )

        result = await service.generate("Test prompt")

        assert result == "Generated text"

    async def test_generate_uses_low_temperature(self):
        """Test that generate uses low temperature for deterministic output."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("Prompt")

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0.3

    async def test_generate_custom_max_tokens(self):
        """Test generate with custom max_tokens."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("Prompt", max_tokens=500)

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == 500

    async def test_generate_default_max_tokens(self):
        """Test generate uses default max_tokens of 200."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("Prompt")

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == 200

    async def test_generate_raises_on_error(self):
        """Test that generate raises exception on API error."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with pytest.raises(Exception, match="API error"):
            await service.generate("Prompt")

    async def test_generate_sends_correct_message_format(self):
        """Test that generate sends simple user message format."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("My prompt")

        call_args = service.client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "My prompt"


class TestLLMServiceClose:
    """Tests for LLMService.close method."""

    async def test_close_calls_close(self):
        """Test that close method calls close on the client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()

        await service.close()

        service.client.close.assert_called_once()

    async def test_close_integration(self):
        """Test close with real client (integration-style)."""
        service = LLMService(api_key="test-key")

        # Should not raise
        await service.close()
