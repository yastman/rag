"""Unit tests for telegram_bot/services/llm.py."""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

import telegram_bot.services as services
from telegram_bot.services.llm import LLMService


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


class TestLLMServiceInit:
    """Test LLMService initialization."""

    def test_init_defaults(self):
        """Test initialization with default values."""
        service = LLMService(api_key="test-key")

        assert service.api_key == "test-key"
        assert service.base_url == "https://api.openai.com/v1"
        assert service.model == "gpt-4o-mini"

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        service = LLMService(
            api_key="custom-key",
            base_url="https://custom.api.com/v1/",
            model="custom-model",
        )

        assert service.api_key == "custom-key"
        assert service.base_url == "https://custom.api.com/v1"  # Trailing slash removed
        assert service.model == "custom-model"

    def test_init_creates_openai_client(self):
        """Test that AsyncOpenAI client is created."""
        from openai import AsyncOpenAI

        service = LLMService(api_key="test-key")

        assert service.client is not None
        assert isinstance(service.client, AsyncOpenAI)

    def test_services_package_no_longer_exports_llmservice(self):
        """Package-level API should steer callers to generate_response()."""
        assert "LLMService" not in services.__all__
        assert not hasattr(services, "LLMService")


class TestFormatContext:
    """Test context formatting."""

    def test_format_context_empty(self):
        """Test formatting with empty chunks."""
        service = LLMService(api_key="test-key")

        result = service._format_context([])

        assert result == "Релевантной информации не найдено."

    def test_format_context_single_chunk(self):
        """Test formatting with single chunk."""
        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Sample apartment text",
                "metadata": {"title": "Apartment 1", "city": "Varna", "price": 50000},
                "score": 0.95,
            }
        ]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "релевантность" not in result  # RRF scores removed (#566)
        assert "Название: Apartment 1" in result
        assert "Город: Varna" in result
        assert "50,000€" in result
        assert "Sample apartment text" in result

    def test_format_context_multiple_chunks(self):
        """Test formatting with multiple chunks."""
        service = LLMService(api_key="test-key")

        chunks = [
            {"text": "Text 1", "metadata": {}, "score": 0.9},
            {"text": "Text 2", "metadata": {}, "score": 0.8},
        ]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "[Объект 2]" in result
        assert "---" in result  # Separator

    def test_format_context_minimal_metadata(self):
        """Test formatting with minimal metadata."""
        service = LLMService(api_key="test-key")

        chunks = [{"text": "Just text", "score": 0.75}]

        result = service._format_context(chunks)

        assert "Just text" in result
        assert "релевантность" not in result  # RRF scores removed (#566)


class TestGetFallbackAnswer:
    """Test fallback answer generation."""

    def test_fallback_no_chunks(self):
        """Test fallback with no chunks."""
        service = LLMService(api_key="test-key")

        result = service._get_fallback_answer("query", [])

        assert "⚠️" in result
        assert "Извините" in result
        assert "недоступен" in result

    def test_fallback_with_chunks(self):
        """Test fallback with chunks returns formatted results."""
        service = LLMService(api_key="test-key")

        chunks = [
            {
                "text": "Apt 1",
                "metadata": {
                    "title": "Nice apartment",
                    "price": 45000,
                    "city": "Burgas",
                    "rooms": 2,
                },
            },
            {
                "text": "Apt 2",
                "metadata": {"title": "Beach view", "price": 75000, "city": "Nesebar"},
            },
        ]

        result = service._get_fallback_answer("query", chunks)

        assert "⚠️" in result
        assert "Nice apartment" in result
        assert "45,000€" in result
        assert "Burgas" in result
        assert "Beach view" in result

    def test_fallback_limits_to_three_chunks(self):
        """Test that fallback only shows 3 chunks."""
        service = LLMService(api_key="test-key")

        chunks = [{"text": f"Chunk {i}", "metadata": {"title": f"Title {i}"}} for i in range(5)]

        result = service._get_fallback_answer("query", chunks)

        assert "Title 0" in result
        assert "Title 1" in result
        assert "Title 2" in result
        assert "Title 3" not in result  # Should be excluded

    def test_fallback_handles_non_numeric_price(self):
        """Test fallback handles string price."""
        service = LLMService(api_key="test-key")

        chunks = [{"text": "Text", "metadata": {"price": "negotiable"}}]

        result = service._get_fallback_answer("query", chunks)

        assert "negotiable€" in result


class TestGenerateAnswer:
    """Test answer generation."""

    async def test_generate_answer_success(self):
        """Test successful answer generation."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Generated answer")
        )

        result = await service.generate_answer(
            question="What apartments?",
            context_chunks=[{"text": "Some context", "score": 0.9}],
        )

        assert result == "Generated answer"

    async def test_generate_answer_timeout(self):
        """Test timeout returns fallback."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        result = await service.generate_answer(
            question="What apartments?",
            context_chunks=[{"text": "Context", "metadata": {"title": "Apt"}}],
        )

        assert "⚠️" in result
        assert "Apt" in result

    async def test_generate_answer_http_error(self):
        """Test API error returns fallback."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )

        result = await service.generate_answer(
            question="What?",
            context_chunks=[],
        )

        assert "⚠️" in result

    async def test_generate_answer_custom_system_prompt(self):
        """Test using custom system prompt."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("Answer"))

        await service.generate_answer(
            question="Q?",
            context_chunks=[],
            system_prompt="Custom prompt",
        )

        call_args = service.client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert messages[0]["content"] == "Custom prompt"


class TestGenerate:
    """Test simple text generation."""

    async def test_generate_success(self):
        """Test successful text generation."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("Result"))

        result = await service.generate("Test prompt")

        assert result == "Result"

    async def test_generate_uses_low_temperature(self):
        """Test that generate uses low temperature (0.3)."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("Result"))

        await service.generate("Prompt")

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0.3

    async def test_generate_custom_max_tokens(self):
        """Test generate with custom max_tokens."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("Result"))

        await service.generate("Prompt", max_tokens=500)

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == 500

    async def test_generate_raises_on_error(self):
        """Test that generate raises exceptions (doesn't use fallback)."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception, match="API Error"):
            await service.generate("Prompt")


class TestClose:
    """Test client closing."""

    async def test_close_closes_client(self):
        """Test that close() closes the client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()

        await service.close()

        service.client.close.assert_called_once()


class TestOpenAISDKMigration:
    """Test that LLMService uses OpenAI SDK instead of raw httpx."""

    def test_uses_openai_sdk_not_httpx(self):
        """Verify LLMService uses openai.AsyncOpenAI, not raw httpx."""
        from openai import AsyncOpenAI

        service = LLMService(api_key="test-key", base_url="http://fake:4000")
        assert hasattr(service, "client")
        assert isinstance(service.client, AsyncOpenAI)
