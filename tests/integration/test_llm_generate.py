"""Test LLMService.generate() and generate_answer() methods."""

from unittest.mock import AsyncMock, MagicMock, patch


async def test_llm_service_has_generate_method():
    """LLMService should have generate() method."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")
    assert hasattr(service, "generate"), "LLMService missing generate() method"
    await service.close()


async def test_generate_returns_text():
    """generate() should return text from LLM."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")

    mock_message = MagicMock()
    mock_message.content = '{"cities": ["София"]}'
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(
        service.client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        result = await service.generate("Extract cities from: квартира в Софии")
        assert result == '{"cities": ["София"]}'
        mock_create.assert_called_once()

    await service.close()


async def test_generate_uses_low_temperature():
    """generate() should use low temperature for structured output."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")

    mock_message = MagicMock()
    mock_message.content = "test"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(
        service.client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        await service.generate("test prompt", max_tokens=100)
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    await service.close()


class TestLLMServiceFormatContext:
    """Tests for _format_context method."""

    def test_format_context_empty_chunks(self):
        """Empty chunks returns default message."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        result = service._format_context([])

        assert "не найдено" in result

    def test_format_context_single_chunk(self):
        """Single chunk formats correctly."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        chunks = [{"text": "Test content", "metadata": {"title": "Test Title"}, "score": 0.95}]
        result = service._format_context(chunks)

        assert "Test Title" in result
        assert "Test content" in result
        assert "0.95" in result

    def test_format_context_multiple_chunks(self):
        """Multiple chunks format with separators."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        chunks = [
            {"text": "Content 1", "metadata": {}, "score": 0.9},
            {"text": "Content 2", "metadata": {}, "score": 0.8},
        ]
        result = service._format_context(chunks)

        assert "Content 1" in result
        assert "Content 2" in result
        assert "---" in result  # Separator

    def test_format_context_with_metadata(self):
        """Context includes metadata fields."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        chunks = [
            {
                "text": "Apartment info",
                "metadata": {"title": "Studio", "city": "Бургас", "price": 50000},
                "score": 0.9,
            }
        ]
        result = service._format_context(chunks)

        assert "Studio" in result
        assert "Бургас" in result
        assert "50,000€" in result


class TestLLMServiceFallback:
    """Tests for _get_fallback_answer method."""

    def test_fallback_no_chunks(self):
        """Fallback with no chunks returns error message."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        result = service._get_fallback_answer("test query", [])

        assert "недоступен" in result
        assert "повторить" in result

    def test_fallback_with_chunks(self):
        """Fallback with chunks returns formatted results."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        chunks = [
            {"text": "Content", "metadata": {"title": "Test Apartment", "price": 45000}},
        ]
        result = service._get_fallback_answer("test query", chunks)

        assert "Test Apartment" in result
        assert "45,000€" in result

    def test_fallback_limits_to_three(self):
        """Fallback only shows first 3 chunks."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")
        chunks = [{"text": f"Content {i}", "metadata": {"title": f"Item {i}"}} for i in range(5)]
        result = service._get_fallback_answer("test query", chunks)

        assert "Item 0" in result
        assert "Item 1" in result
        assert "Item 2" in result
        assert "Item 3" not in result
        assert "Item 4" not in result


class TestLLMServiceGenerateAnswer:
    """Tests for generate_answer method."""

    async def test_generate_answer_success(self):
        """generate_answer returns LLM response."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")

        mock_message = MagicMock()
        mock_message.content = "Generated answer"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch.object(
            service.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            result = await service.generate_answer(
                "Test question", [{"text": "Context", "metadata": {}, "score": 0.9}]
            )
            assert result == "Generated answer"

        await service.close()

    async def test_generate_answer_uses_system_prompt(self):
        """generate_answer includes system prompt in messages."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")

        mock_message = MagicMock()
        mock_message.content = "Answer"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch.object(
            service.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            await service.generate_answer(
                "Question",
                [{"text": "Context", "metadata": {}, "score": 0.9}],
                system_prompt="Custom system prompt",
            )
            call_kwargs = mock_create.call_args[1]
            messages = call_kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "Custom system prompt"

        await service.close()

    async def test_generate_answer_fallback_on_timeout(self):
        """generate_answer returns fallback on timeout."""
        import openai

        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")

        with patch.object(
            service.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = openai.APITimeoutError(request=MagicMock())
            result = await service.generate_answer(
                "Question",
                [{"text": "Context", "metadata": {"title": "Fallback Item"}, "score": 0.9}],
            )
            assert "недоступен" in result
            assert "Fallback Item" in result

        await service.close()

    async def test_generate_answer_fallback_on_http_error(self):
        """generate_answer returns fallback on generic error."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", base_url="https://api.test.com")

        with patch.object(
            service.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = Exception("Server Error")
            result = await service.generate_answer("Question", [])
            assert "недоступен" in result

        await service.close()
