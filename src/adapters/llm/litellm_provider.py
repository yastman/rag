"""Compatibility LLM adapter backed by the canonical LiteLLM SDK router."""

import logging
import os
from typing import Any

from src.adapters.llm.base import (
    LLMAuthenticationError,
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMTimeoutError,
)


logger = logging.getLogger(__name__)


class LiteLlmProvider(LLMProvider):
    """LLM adapter using the process-local LiteLLM router.

    This class remains for older adapter/factory call sites, but it no longer
    opens a second LiteLLM path via ``litellm.acompletion``. All chat text
    generation goes through :mod:`src.runtime.llm.router`, the same
    OpenAI-shaped client used by ``GraphConfig.create_llm()``.
    """

    def __init__(self, default_model: str = "gpt-4o-mini") -> None:
        self.default_model = default_model
        try:
            self.timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        except ValueError:
            self.timeout_seconds = 60.0

    async def generate(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a response through the canonical LiteLLM router client."""
        from litellm.exceptions import AuthenticationError, RateLimitError, Timeout

        from src.runtime.llm import create_litellm_chat_client

        target_model = model or self.default_model
        kwargs.setdefault("timeout", self.timeout_seconds)

        try:
            client = create_litellm_chat_client(
                model=target_model,
                timeout=float(kwargs.pop("timeout")),
            )
            response = await client.chat.completions.create(
                messages=messages,
                **kwargs,
            )
            return response.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise LLMAuthenticationError(str(exc), raw_error=exc) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(str(exc), raw_error=exc) from exc
        except Timeout as exc:
            raise LLMTimeoutError(str(exc), raw_error=exc) from exc
        except Exception as exc:
            raise LLMError(
                f"LiteLLM router call failed: {exc}", error_type="api_error", raw_error=exc
            ) from exc
