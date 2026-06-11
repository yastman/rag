"""Factory for LLM providers."""

import os

from src.adapters.llm.base import LLMProvider
from src.adapters.llm.litellm_provider import LiteLlmProvider


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """Return the configured LLMProvider instance.

    Args:
        provider_name: Optional provider name. If not supplied, read from
          the LLM_PROVIDER environment variable, defaulting to 'litellm'.

    Returns:
        An instance of LLMProvider.

    Raises:
        ValueError: If the provider name is unknown.
    """
    name: str = (provider_name or os.getenv("LLM_PROVIDER") or "litellm").strip().lower()

    if name == "litellm":
        return LiteLlmProvider()
    raise ValueError(f"Unknown LLM provider: '{name}'. Supported providers: 'litellm'.")
