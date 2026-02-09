"""Langfuse CallbackHandler factory for LangGraph integration."""

from __future__ import annotations

import logging
import os
from typing import Any


logger = logging.getLogger(__name__)


def create_langfuse_handler(
    session_id: str,
    user_id: str,
    tags: list[str] | None = None,
) -> Any | None:
    """Create a Langfuse CallbackHandler if credentials are configured.

    Returns None if LANGFUSE_SECRET_KEY is not set, allowing graceful
    degradation when Langfuse is not available.
    """
    if not os.environ.get("LANGFUSE_SECRET_KEY"):
        logger.debug("Langfuse disabled: LANGFUSE_SECRET_KEY not set")
        return None

    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(
            session_id=session_id,
            user_id=user_id,
            tags=tags or ["telegram", "rag", "langgraph"],
        )
    except Exception:
        logger.warning("Failed to create Langfuse handler", exc_info=True)
        return None
