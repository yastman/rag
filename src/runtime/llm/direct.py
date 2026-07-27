"""Direct LiteLLM boundary for the local-only RAG API."""

from __future__ import annotations

import json
from typing import Any

import litellm
from pydantic import BaseModel, ValidationError

from src.adapters.llm.base import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)


class _StructuredAnswer(BaseModel):
    answer: str


class _Completions:
    def __init__(self, provider: DirectLiteLlmProvider) -> None:
        self._provider = provider

    async def create(self, *, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        response = await self._provider.acompletion(messages, **kwargs)
        try:
            content = response.choices[0].message.content
            answer = _StructuredAnswer.model_validate_json(content).answer
        except (
            AttributeError,
            IndexError,
            TypeError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            raise LLMError("Invalid structured response from Cerebras", raw_error=exc) from exc
        response.choices[0].message.content = answer
        return response


class _Chat:
    def __init__(self, provider: DirectLiteLlmProvider) -> None:
        self.completions = _Completions(provider)


class DirectLiteLlmProvider:
    """One direct, non-retrying Cerebras completion boundary."""

    def __init__(
        self,
        *,
        model: str = "cerebras/gpt-oss-120b",
        api_key: str | None = None,
        timeout: float = 30.0,
        session: Any | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.session = session
        self.chat = _Chat(self)

    async def acompletion(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        completion_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "api_key": self.api_key,
            "timeout": self.timeout,
            "shared_session": self.session,
            "response_format": response_format or {"type": "json_object"},
            **kwargs,
        }
        try:
            return await litellm.acompletion(**completion_kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    @staticmethod
    def _normalize_error(exc: Exception) -> LLMError:
        message = str(exc)
        if isinstance(exc, litellm.AuthenticationError):
            return LLMAuthenticationError(message, raw_error=exc)
        if isinstance(exc, litellm.RateLimitError):
            return LLMRateLimitError(message, raw_error=exc)
        if isinstance(exc, litellm.Timeout):
            return LLMTimeoutError(message, raw_error=exc)
        if isinstance(exc, (litellm.APIConnectionError, ConnectionError)):
            return LLMConnectionError(message, raw_error=exc)
        return LLMError(message, raw_error=exc)
