"""LLM error types for runtime consumers."""

from src.adapters.llm.base import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)


__all__ = [
    "LLMAuthenticationError",
    "LLMError",
    "LLMRateLimitError",
    "LLMTimeoutError",
]
