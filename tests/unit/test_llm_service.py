"""Unit tests for telegram_bot/services/llm.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.services.llm import LLMService


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

    def test_init_creates_http_client(self):
        """Test that HTTP client is created."""
        service = LLMService(api_key="test-key")

        assert service.client is not None
        assert isinstance(service.client, httpx.AsyncClient)


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
        assert "релевантность: 0.95" in result
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
        assert "релевантность: 0.75" in result


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
                "metadata": {"title": "Nice apartment", "price": 45000, "city": "Burgas", "rooms": 2},
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

        chunks = [
            {"text": f"Chunk {i}", "metadata": {"title": f"Title {i}"}} for i in range(5)
        ]

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

    @pytest.mark.asyncio
    async def test_generate_answer_success(self):
        """Test successful answer generation."""
        service = LLMService(api_key="test-key")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Generated answer"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await service.generate_answer(
                question="What apartments?",
                context_chunks=[{"text": "Some context", "score": 0.9}],
            )

            assert result == "Generated answer"

    @pytest.mark.asyncio
    async def test_generate_answer_timeout(self):
        """Test timeout returns fallback."""
        service = LLMService(api_key="test-key")

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            result = await service.generate_answer(
                question="What apartments?",
                context_chunks=[{"text": "Context", "metadata": {"title": "Apt"}}],
            )

            assert "⚠️" in result
            assert "Apt" in result

    @pytest.mark.asyncio
    async def test_generate_answer_http_error(self):
        """Test HTTP error returns fallback."""
        service = LLMService(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=mock_response
            )

            result = await service.generate_answer(
                question="What?",
                context_chunks=[],
            )

            assert "⚠️" in result

    @pytest.mark.asyncio
    async def test_generate_answer_custom_system_prompt(self):
        """Test using custom system prompt."""
        service = LLMService(api_key="test-key")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Answer"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await service.generate_answer(
                question="Q?",
                context_chunks=[],
                system_prompt="Custom prompt",
            )

            # Verify the custom prompt was used
            call_args = mock_post.call_args
            json_data = call_args[1]["json"]
            assert json_data["messages"][0]["content"] == "Custom prompt"


class TestGenerate:
    """Test simple text generation."""

    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful text generation."""
        service = LLMService(api_key="test-key")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Result"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await service.generate("Test prompt")

            assert result == "Result"

    @pytest.mark.asyncio
    async def test_generate_uses_low_temperature(self):
        """Test that generate uses low temperature (0.3)."""
        service = LLMService(api_key="test-key")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Result"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await service.generate("Prompt")

            json_data = mock_post.call_args[1]["json"]
            assert json_data["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_generate_custom_max_tokens(self):
        """Test generate with custom max_tokens."""
        service = LLMService(api_key="test-key")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Result"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await service.generate("Prompt", max_tokens=500)

            json_data = mock_post.call_args[1]["json"]
            assert json_data["max_tokens"] == 500

    @pytest.mark.asyncio
    async def test_generate_raises_on_error(self):
        """Test that generate raises exceptions (doesn't use fallback)."""
        service = LLMService(api_key="test-key")

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("API Error")

            with pytest.raises(Exception):
                await service.generate("Prompt")


class TestClose:
    """Test client closing."""

    @pytest.mark.asyncio
    async def test_close_closes_client(self):
        """Test that close() closes the HTTP client."""
        service = LLMService(api_key="test-key")

        with patch.object(service.client, "aclose", new_callable=AsyncMock) as mock_close:
            await service.close()

            mock_close.assert_called_once()
