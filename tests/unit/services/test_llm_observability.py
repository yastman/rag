# tests/unit/services/test_llm_observability.py
"""Unit tests for LLMService Langfuse instrumentation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLLMServiceObservability:
    """Tests for LLMService @observe decorators."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService with mocked HTTP client."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(
            api_key="test-key",
            base_url="http://localhost:4000",
            model="gpt-4o-mini",
        )
        service.client = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_generate_answer_updates_generation(self, llm_service):
        """generate_answer should call update_current_generation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test answer"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        llm_service.client.post = AsyncMock(return_value=mock_response)

        with patch("telegram_bot.services.llm.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await llm_service.generate_answer(
                question="Test question",
                context_chunks=[{"text": "Context"}],
            )

            # Should be called twice: once at start, once with usage
            assert mock_langfuse.update_current_generation.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_answer_tracks_model(self, llm_service):
        """generate_answer should track model name."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Answer"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        llm_service.client.post = AsyncMock(return_value=mock_response)

        with patch("telegram_bot.services.llm.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await llm_service.generate_answer("Test", [{"text": "Context"}])

            first_call = mock_langfuse.update_current_generation.call_args_list[0]
            assert first_call.kwargs["model"] == "gpt-4o-mini"
