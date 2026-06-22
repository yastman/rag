"""LLM chat.completions call wrappers and compatibility helpers (#3015)."""

from __future__ import annotations

from typing import Any


async def _chat_create_with_optional_name(
    llm: Any,
    *,
    observation_name: str,
    **kwargs: Any,
) -> Any:
    """Call chat.completions.create, stripping Langfuse-specific kwargs (removed in #2844)."""
    kwargs.pop("langfuse_prompt", None)
    return await llm.chat.completions.create(**kwargs)
