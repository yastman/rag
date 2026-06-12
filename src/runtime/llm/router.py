"""LiteLLM Python SDK router for chat completions.

The repository uses this in-process LiteLLM SDK router. Runtime code calls this
in-process router instead, preserving the OpenAI chat-completions response shape
that graph nodes already consume while keeping the previous fallback chain.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from litellm import Router
from pydantic import BaseModel


DEFAULT_MODEL_ALIAS = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_NUM_RETRIES = 2


def _env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback)


def _optional_api_key(name: str, fallback: str = "") -> str | None:
    value = _env(name, fallback).strip()
    return value or None


def build_model_list() -> list[dict[str, Any]]:
    """Build the canonical LiteLLM SDK-router model list."""
    cerebras_key = _optional_api_key("CEREBRAS_API_KEY", _env("LLM_API_KEY"))
    groq_key = _optional_api_key("GROQ_API_KEY")
    openai_key = _optional_api_key("OPENAI_API_KEY")
    return [
        {
            "model_name": DEFAULT_MODEL_ALIAS,
            "litellm_params": {
                "model": _env("LITELLM_PRIMARY_MODEL", "cerebras/zai-glm-4.7"),
                "api_key": cerebras_key,
                "max_completion_tokens": int(_env("LITELLM_PRIMARY_MAX_TOKENS", "512")),
                "disable_reasoning": True,
                "timeout": float(_env("LITELLM_PRIMARY_TIMEOUT", "30")),
                "stream_timeout": float(_env("LITELLM_PRIMARY_STREAM_TIMEOUT", "5")),
            },
        },
        {
            "model_name": "gpt-oss-120b",
            "litellm_params": {
                "model": _env("LITELLM_REASONING_MODEL", "cerebras/gpt-oss-120b"),
                "api_key": cerebras_key,
                "max_completion_tokens": int(_env("LITELLM_REASONING_MAX_TOKENS", "1024")),
                "merge_reasoning_content_in_choices": True,
            },
        },
        {
            "model_name": "gpt-4o-mini-cerebras-oss",
            "litellm_params": {
                "model": _env("LITELLM_CEREBRAS_FALLBACK_MODEL", "cerebras/gpt-oss-120b"),
                "api_key": cerebras_key,
                "max_completion_tokens": int(_env("LITELLM_REASONING_MAX_TOKENS", "1024")),
                "merge_reasoning_content_in_choices": True,
            },
        },
        {
            "model_name": "gpt-4o-mini-fallback",
            "litellm_params": {
                "model": _env("LITELLM_GROQ_FALLBACK_MODEL", "groq/llama-3.1-70b-versatile"),
                "api_key": groq_key,
            },
        },
        {
            "model_name": "gpt-4o-mini-openai",
            "litellm_params": {
                "model": _env("LITELLM_OPENAI_FALLBACK_MODEL", "openai/gpt-4o-mini"),
                "api_key": openai_key,
            },
        },
    ]


@lru_cache(maxsize=1)
def get_litellm_router() -> Router:
    """Return the process-local LiteLLM Router with retries and fallbacks."""
    fallbacks = [
        {
            DEFAULT_MODEL_ALIAS: [
                "gpt-4o-mini-cerebras-oss",
                "gpt-4o-mini-fallback",
                "gpt-4o-mini-openai",
            ]
        },
        {
            "gpt-oss-120b": [
                "gpt-4o-mini-cerebras-oss",
                "gpt-4o-mini-fallback",
                "gpt-4o-mini-openai",
            ]
        },
    ]
    return Router(
        model_list=build_model_list(),
        fallbacks=fallbacks,
        num_retries=int(_env("LITELLM_NUM_RETRIES", str(DEFAULT_NUM_RETRIES))),
        timeout=float(_env("LITELLM_REQUEST_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))),
    )


def _json_schema_response_format(response_model: type[BaseModel]) -> dict[str, Any]:
    """Return LiteLLM/OpenAI JSON-schema response_format for a Pydantic model."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "schema": response_model.model_json_schema(),
            "strict": True,
        },
    }


def _completion_message_content(response: Any) -> Any:
    """Extract first chat-completion message content from object or dict responses."""
    if isinstance(response, dict):
        return response.get("choices", [{}])[0].get("message", {}).get("content", "")
    return response.choices[0].message.content


def _parse_structured_response(response: Any, response_model: type[BaseModel]) -> BaseModel:
    """Parse a LiteLLM chat completion into ``response_model``."""
    if isinstance(response, response_model):
        return response
    content = _completion_message_content(response)
    if isinstance(content, response_model):
        return content
    if isinstance(content, dict):
        return response_model.model_validate(content)
    if not isinstance(content, str):
        return response_model.model_validate(content)
    try:
        return response_model.model_validate_json(content)
    except ValueError:
        return response_model.model_validate(json.loads(content))


@dataclass(slots=True)
class _ChatCompletions:
    router: Router
    default_model: str
    timeout: float

    async def create(self, **kwargs: Any) -> Any:
        """Call ``Router.acompletion`` with OpenAI-compatible kwargs.

        ``response_model`` is an Instructor-compatibility shim used during the
        LiteLLM consolidation: it is translated to OpenAI JSON-schema
        ``response_format`` and parsed locally, so callers keep one SDK-router
        path without importing Instructor.
        """
        request = dict(kwargs)
        response_model = request.pop("response_model", None)
        request.pop("max_retries", None)
        request.pop("name", None)  # OpenAI wrapper-only metadata; LiteLLM drops unsupported params.
        request.pop("langfuse_prompt", None)
        request.setdefault("model", self.default_model)
        request.setdefault("timeout", self.timeout)
        if response_model is not None and "response_format" not in request:
            request["response_format"] = _json_schema_response_format(response_model)
        response = await self.router.acompletion(**request)
        if response_model is None:
            return response
        return _parse_structured_response(response, response_model)


@dataclass(slots=True)
class _ChatNamespace:
    completions: _ChatCompletions


@dataclass(slots=True)
class LiteLLMChatClient:
    """Small OpenAI-shaped async chat client backed by LiteLLM Router."""

    router: Router
    default_model: str = DEFAULT_MODEL_ALIAS
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    chat: _ChatNamespace = field(init=False)
    _langfuse_auto_trace: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chat",
            _ChatNamespace(
                completions=_ChatCompletions(
                    router=self.router,
                    default_model=self.default_model,
                    timeout=self.timeout,
                )
            ),
        )
        object.__setattr__(self, "_langfuse_auto_trace", False)


def create_litellm_chat_client(
    *,
    model: str | None = None,
    router: Router | None = None,
    timeout: float | None = None,
) -> LiteLLMChatClient:
    """Create an OpenAI-shaped chat client backed by the LiteLLM Python SDK."""
    return LiteLLMChatClient(
        router=router or get_litellm_router(),
        default_model=model or DEFAULT_MODEL_ALIAS,
        timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
    )
