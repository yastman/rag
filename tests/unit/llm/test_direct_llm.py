"""Focused contract tests for the local direct LiteLLM boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.llm.base import LLMAuthenticationError, LLMConnectionError, LLMError
from src.runtime.llm.direct import DirectLiteLlmProvider


async def test_acompletion_calls_litellm_directly_with_fixed_local_contract() -> None:
    session = object()
    provider = DirectLiteLlmProvider(api_key="key", session=session)
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content='{"answer":"yes"}'))]
    response.model = "cerebras/gpt-oss-120b"

    with (
        patch(
            "src.runtime.llm.direct.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=response,
        ) as complete,
        patch("src.runtime.llm.direct.litellm.Router") as router,
    ):
        result = await provider.acompletion([{"role": "user", "content": "hi"}])

    assert result == response
    router.assert_not_called()
    assert complete.await_args.kwargs == {
        "model": "cerebras/gpt-oss-120b",
        "messages": [{"role": "user", "content": "hi"}],
        "api_key": "key",
        "timeout": 30.0,
        "shared_session": session,
        "response_format": {"type": "json_object"},
    }


async def test_acompletion_normalizes_provider_errors() -> None:
    provider = DirectLiteLlmProvider()

    with patch(
        "src.runtime.llm.direct.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=ConnectionError("offline"),
    ):
        with pytest.raises(LLMConnectionError, match="offline"):
            await provider.acompletion([{"role": "user", "content": "hi"}])


async def test_acompletion_preserves_litellm_authentication_error() -> None:
    class AuthenticationError(Exception):
        pass

    provider = DirectLiteLlmProvider()

    with (
        patch("src.runtime.llm.direct.litellm.AuthenticationError", AuthenticationError),
        patch(
            "src.runtime.llm.direct.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=AuthenticationError("bad key"),
        ),
    ):
        with pytest.raises(LLMAuthenticationError, match="bad key"):
            await provider.acompletion([{"role": "user", "content": "hi"}])


async def test_chat_completion_extracts_validated_json_answer() -> None:
    provider = DirectLiteLlmProvider()
    provider.acompletion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer":"grounded"}'))],
            model="cerebras/gpt-oss-120b",
        )
    )

    result = await provider.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

    assert result.choices[0].message.content == "grounded"


async def test_chat_completion_rejects_malformed_json() -> None:
    provider = DirectLiteLlmProvider()
    provider.acompletion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))],
            model="cerebras/gpt-oss-120b",
        )
    )

    with pytest.raises(LLMError, match="Invalid structured response"):
        await provider.chat.completions.create(messages=[{"role": "user", "content": "hi"}])
