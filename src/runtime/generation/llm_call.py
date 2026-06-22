"""LLM chat.completions call wrappers and compatibility helpers (#3015)."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def _is_unsupported_name_kwarg(exc: TypeError) -> bool:
    msg = str(exc)
    return "unexpected keyword argument" in msg and "'name'" in msg


async def _chat_create_with_optional_name(
    llm: Any,
    *,
    observation_name: str,
    **kwargs: Any,
) -> Any:
    """Call chat.completions.create with `name`, retrying without it if unsupported."""
    create_fn = llm.chat.completions.create
    try:
        return await create_fn(name=observation_name, **kwargs)
    except TypeError as exc:
        if not _is_unsupported_name_kwarg(exc):
            raise
        logger.debug("LLM client does not support `name`; retrying without it")
        return await create_fn(**kwargs)
