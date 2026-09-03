"""Native LiteLLM SDK boundary for chat text, structured output and streaming.

Runtime code calls the in-process LiteLLM SDK Router through this module —
the one small native interface replacing the former OpenAI-shaped
``chat.completions.create`` shim (#3223). Provider priority, retries and
Cerebras/Groq/OpenAI fallback stay in the Router configuration below
(unchanged); schema translation, connection-error normalization and
observation naming live here so call sites never reintroduce shim kwargs.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from litellm import Router
from pydantic import BaseModel

from src.adapters.llm.base import LLMConnectionError


logger = logging.getLogger(__name__)


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


def json_schema_response_format(response_model: type[BaseModel]) -> dict[str, Any]:
    """Return the LiteLLM/OpenAI JSON-schema ``response_format`` for a Pydantic model."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "schema": response_model.model_json_schema(),
            "strict": True,
        },
    }


def parse_structured_response(response: Any, response_model: type[BaseModel]) -> BaseModel:
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


def _completion_message_content(response: Any) -> Any:
    """Extract first chat-completion message content from object or dict responses."""
    if isinstance(response, dict):
        return response.get("choices", [{}])[0].get("message", {}).get("content", "")
    return response.choices[0].message.content


def normalize_connection_error(exc: BaseException) -> LLMConnectionError | None:
    """Normalize a LiteLLM connection failure into the shared app error type.

    Returns ``None`` for any other exception so callers can re-raise unchanged.
    """
    from litellm.exceptions import APIConnectionError

    if isinstance(exc, APIConnectionError):
        return LLMConnectionError(str(exc), raw_error=exc)
    return None


@dataclass(slots=True)
class LiteLlmClient:
    """Native async LiteLLM SDK boundary over the process-local Router.

    One interface, three verbs:

    - :meth:`completion` — one ``Router.acompletion`` call returning the
      native LiteLLM response (text, ``response_format``, ``stream=False``).
    - :meth:`structured` — Pydantic model in, validated instance out.
    - :meth:`stream` — ``Router.acompletion(stream=True)`` returning the
      native async chunk iterator.

    ``observation_name`` is call-site observability metadata only; it is
    logged and never forwarded to the SDK. All other kwargs pass through to
    ``acompletion`` unchanged.
    """

    router: Router
    default_model: str = DEFAULT_MODEL_ALIAS
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    async def completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        observation_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run one native ``Router.acompletion`` call and return its response."""
        target_model = model or self.default_model
        if observation_name:
            logger.debug("LLM completion '%s' (model=%s)", observation_name, target_model)
        request: dict[str, Any] = {"model": target_model, "messages": messages, **kwargs}
        request.setdefault("timeout", self.timeout)
        return await self.router.acompletion(**request)

    async def structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        model: str | None = None,
        observation_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Structured-output call: Pydantic schema in, validated instance out."""
        if "response_format" not in kwargs:
            kwargs["response_format"] = json_schema_response_format(response_model)
        response = await self.completion(
            messages=messages,
            model=model,
            observation_name=observation_name,
            **kwargs,
        )
        return parse_structured_response(response, response_model)

    async def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        observation_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Return the native async chunk iterator from a streaming completion."""
        return await self.completion(
            messages=messages,
            model=model,
            observation_name=observation_name,
            stream=True,
            **kwargs,
        )


def create_llm_client(
    *,
    model: str | None = None,
    router: Router | None = None,
    timeout: float | None = None,
) -> LiteLlmClient:
    """Create the native LiteLLM SDK client backed by the process-local Router."""
    return LiteLlmClient(
        router=router or get_litellm_router(),
        default_model=model or DEFAULT_MODEL_ALIAS,
        timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
    )
