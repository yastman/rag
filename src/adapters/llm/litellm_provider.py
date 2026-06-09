"""LiteLLM adapter for text generation."""

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
    """LiteLLM adapter using litellm Python package."""

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
        """Generate a response using litellm.acompletion."""
        import litellm
        from litellm.exceptions import AuthenticationError, RateLimitError, Timeout

        target_model = model or self.default_model
        kwargs.setdefault("timeout", self.timeout_seconds)

        try:
            response = await litellm.acompletion(
                model=target_model,
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
                f"LiteLLM call failed: {exc}", error_type="api_error", raw_error=exc
            ) from exc
