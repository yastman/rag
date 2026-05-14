"""Tests for Langfuse OpenAI trace context (#1362).

When ``langfuse.openai.AsyncOpenAI`` auto-traces every completion call without
awareness of the active trace, it creates orphan ``litellm-acompletion`` root
traces.  These tests verify that:

1. ``GraphConfig.create_llm(auto_trace=False)`` returns a plain
   ``openai.AsyncOpenAI`` client that does NOT auto-trace.
2. ``_chat_create_with_optional_name`` skips the Langfuse ``name`` kwarg
   when the client is plain, avoiding a needless TypeError → retry.
3. ``generate_response`` still records cost and model metadata via the
   explicit ``update_current_generation`` call on the active
   ``service-generate-response`` span — keeping that as the single
   cost-bearing generation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.config import GraphConfig
from telegram_bot.services.generate_response import (
    _chat_create_with_optional_name as _svc_chat_create,
)
from telegram_bot.services.generate_response import (
    generate_response,
)


class TestGraphConfigAutoTrace:
    """Unit tests for GraphConfig.create_llm auto_trace switch."""

    def test_create_llm_default_uses_langfuse_wrapper(self) -> None:
        with (
            patch("langfuse.openai.AsyncOpenAI") as mock_langfuse,
            patch("openai.AsyncOpenAI") as mock_plain,
        ):
            mock_langfuse.return_value = MagicMock()
            cfg = GraphConfig(llm_model="m", llm_base_url="http://test:4000")
            llm = cfg.create_llm()
        assert llm is not None
        mock_langfuse.assert_called_once()
        mock_plain.assert_not_called()

    def test_create_llm_auto_trace_false_uses_plain_openai__graph_config_auto_trace(self) -> None:
        with (
            patch("langfuse.openai.AsyncOpenAI") as mock_langfuse,
            patch("openai.AsyncOpenAI") as mock_plain,
        ):
            mock_plain.return_value = MagicMock()
            cfg = GraphConfig(llm_model="m", llm_base_url="http://test:4000")
            llm = cfg.create_llm(auto_trace=False)
        assert llm is not None
        mock_plain.assert_called_once()
        mock_langfuse.assert_not_called()
        assert getattr(llm, "_langfuse_auto_trace", None) is False


class TestChatCreateWithOptionalName:
    """Unit tests for _chat_create_with_optional_name wrapper."""

    @pytest.mark.asyncio
    async def test_skips_name_when_auto_trace_disabled(self) -> None:
        """Plain client must not receive the Langfuse ``name`` kwarg."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        object.__setattr__(mock_client, "_langfuse_auto_trace", False)

        result = await _svc_chat_create(
            mock_client,
            observation_name="generate-answer",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result is mock_response
        mock_client.chat.completions.create.assert_awaited_once()
        call_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert "name" not in call_kwargs

    @pytest.mark.asyncio
    async def test_retries_without_name_for_plain_openai_fallback(self) -> None:
        """When a plain client lacks the marker, the TypeError fallback still works."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                TypeError("create() got an unexpected keyword argument 'name'"),
                mock_response,
            ]
        )

        result = await _svc_chat_create(
            mock_client,
            observation_name="generate-answer",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result is mock_response
        assert mock_client.chat.completions.create.await_count == 2
        first_call = mock_client.chat.completions.create.await_args_list[0].kwargs
        second_call = mock_client.chat.completions.create.await_args_list[1].kwargs
        assert first_call.get("name") == "generate-answer"
        assert "name" not in second_call

    @pytest.mark.asyncio
    async def test_passes_name_for_langfuse_wrapped_client(self) -> None:
        """Wrapped client (default) receives ``name`` on the first attempt."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await _svc_chat_create(
            mock_client,
            observation_name="generate-answer",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result is mock_response
        mock_client.chat.completions.create.assert_awaited_once()
        call_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert call_kwargs.get("name") == "generate-answer"


class TestGenerateResponseObservability:
    """Integration tests verifying explicit generation stays the single source of truth."""

    @pytest.mark.asyncio
    async def test_uses_plain_client_and_updates_generation(self) -> None:
        """When auto_trace=False, generate_response still records usage explicitly."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Ответ модели"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4o-mini"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 12
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 17
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        object.__setattr__(mock_client, "_langfuse_auto_trace", False)

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.1
        mock_config.generate_max_tokens = 128
        mock_config.streaming_enabled = False
        mock_config.show_sources = False
        mock_config.response_style_enabled = False
        mock_config.response_style_shadow_mode = False
        mock_config.create_llm.return_value = mock_client

        lf = MagicMock()

        result = await generate_response(
            query="Тест",
            documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
            config=mock_config,
            lf_client=lf,
            raw_messages=[{"role": "user", "content": "Тест"}],
        )

        assert result["response"] == "Ответ модели"
        assert result["llm_provider_model"] == "gpt-4o-mini"
        # Plain client → no name kwarg
        call_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert "name" not in call_kwargs
        # Explicit generation update must still happen
        lf.update_current_generation.assert_any_call(
            model="gpt-4o-mini",
            usage_details={"input": 12, "output": 5, "total": 17},
        )

    @pytest.mark.asyncio
    async def test_streaming_plain_client_updates_generation(self) -> None:
        """Streaming path with plain client still records usage via update_current_generation."""

        # Local copies of test helpers (avoid importing from sibling test files)
        class _StreamChunk:
            def __init__(self, content: str, usage=None):
                delta = MagicMock()
                delta.content = content
                choice = MagicMock()
                choice.delta = delta
                self.choices = [choice]
                self.model = "gpt-4o-mini"
                self.usage = usage

        class _AsyncStream:
            def __init__(self, chunks):
                self._chunks = chunks
                self._idx = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._idx >= len(self._chunks):
                    raise StopAsyncIteration
                chunk = self._chunks[self._idx]
                self._idx += 1
                return chunk

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.1
        mock_config.generate_max_tokens = 128
        mock_config.streaming_enabled = True
        mock_config.show_sources = False
        mock_config.response_style_enabled = False
        mock_config.response_style_shadow_mode = False

        usage = MagicMock()
        usage.prompt_tokens = 11
        usage.completion_tokens = 7
        usage.total_tokens = 18
        stream = _AsyncStream([_StreamChunk("Потоковый ответ", usage=usage)])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=stream)
        object.__setattr__(mock_client, "_langfuse_auto_trace", False)
        mock_config.create_llm.return_value = mock_client

        lf = MagicMock()
        bot = AsyncMock()
        bot.send_message_draft = AsyncMock(return_value=True)
        sent_msg = AsyncMock()
        sent_msg.chat = MagicMock(id=555)
        sent_msg.message_id = 777
        message = AsyncMock()
        message.chat = MagicMock(id=555)
        message.bot = bot
        message.answer = AsyncMock(return_value=sent_msg)

        result = await generate_response(
            query="Стриминг",
            documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
            config=mock_config,
            lf_client=lf,
            message=message,
            raw_messages=[{"role": "user", "content": "Стриминг"}],
        )

        assert result["response"] == "Потоковый ответ"
        call_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert "name" not in call_kwargs
        lf.update_current_generation.assert_any_call(
            model="gpt-4o-mini",
            usage_details={"input": 11, "output": 7, "total": 18},
        )
