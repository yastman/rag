# tests/unit/services/test_llm_observability.py
"""Unit tests for LLMService observability.

After migration to OpenAI SDK with Langfuse drop-in replacement,
observability is automatic via `from langfuse.openai import AsyncOpenAI`.
These tests verify the LLMService still works correctly with the new approach.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestLLMServiceObservability:
    """Tests for LLMService observability via Langfuse drop-in replacement."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService with mocked OpenAI client."""
        from telegram_bot.services.llm import LLMService

        return LLMService(
            api_key="test-key",
            base_url="http://localhost:4000",
            model="gpt-4o-mini",
        )

    async def test_generate_answer_passes_name_for_tracing(self, llm_service):
        """generate_answer should pass name parameter for Langfuse tracing."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]

        llm_service.client = AsyncMock()
        llm_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await llm_service.generate_answer(
            question="Test question",
            context_chunks=[{"text": "Context"}],
        )

        call_args = llm_service.client.chat.completions.create.call_args
        assert call_args[1]["name"] == "generate-answer"

    async def test_generate_answer_tracks_model(self, llm_service):
        """generate_answer should use the configured model name."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]

        llm_service.client = AsyncMock()
        llm_service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await llm_service.generate_answer("Test", [{"text": "Context"}])

        call_args = llm_service.client.chat.completions.create.call_args
        assert call_args[1]["model"] == "gpt-4o-mini"
