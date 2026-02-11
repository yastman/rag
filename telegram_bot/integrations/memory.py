"""Checkpointer factory for LangGraph conversation persistence.

Uses AsyncRedisSaver (langgraph-checkpoint-redis SDK) when Redis URL is configured.
Falls back to MemorySaver for dev/testing. Zero custom logic — SDK wiring only.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver


logger = logging.getLogger(__name__)


def create_redis_checkpointer(redis_url: str) -> Any:
    """Create AsyncRedisSaver for persistent conversation memory (SDK).

    Must be called inside a running event loop.
    Caller must: ``await checkpointer.asetup()`` before use.
    """
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    logger.info("Creating AsyncRedisSaver (redis_url=%s...)", redis_url[:30])
    return AsyncRedisSaver(redis_url=redis_url)


def create_fallback_checkpointer() -> MemorySaver:
    """In-memory checkpointer for dev/testing."""
    logger.info("Using MemorySaver (in-memory, non-persistent)")
    return MemorySaver()


# Backward compat: default singleton for dev/tests
checkpointer = MemorySaver()
