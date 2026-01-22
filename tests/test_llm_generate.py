"""Test LLMService.generate() method for CESC."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_llm_service_has_generate_method():
    """LLMService should have generate() method."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")
    assert hasattr(service, "generate"), "LLMService missing generate() method"
    await service.close()


@pytest.mark.asyncio
async def test_generate_returns_text():
    """generate() should return text from LLM."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"cities": ["София"]}'}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await service.generate("Extract cities from: квартира в Софии")
        assert result == '{"cities": ["София"]}'
        mock_post.assert_called_once()

    await service.close()


@pytest.mark.asyncio
async def test_generate_uses_low_temperature():
    """generate() should use low temperature for structured output."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")

    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "test"}}]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        await service.generate("test prompt", max_tokens=100)
        call_args = mock_post.call_args
        assert call_args[1]["json"]["temperature"] == 0.3

    await service.close()
