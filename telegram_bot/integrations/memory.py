"""Checkpointer factory for LangGraph conversation persistence.

Uses AsyncRedisSaver (langgraph-checkpoint-redis SDK) when Redis URL is configured.
Falls back to MemorySaver for dev/testing. Zero custom logic — SDK wiring only.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver


logger = logging.getLogger(__name__)


def create_redis_checkpointer(
    redis_url: str,
    *,
    ttl_minutes: int | None = None,
    refresh_on_read: bool = True,
) -> Any:
    """Create AsyncRedisSaver for persistent conversation memory (SDK).

    Args:
        redis_url: Redis connection string.
        ttl_minutes: Checkpoint TTL in minutes. None = no expiry.
        refresh_on_read: Sliding expiration for active threads.

    Caller must: ``await checkpointer.asetup()`` before use.
    """
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    kwargs: dict[str, Any] = {"redis_url": redis_url}
    if ttl_minutes is not None:
        kwargs["ttl"] = {
            "default_ttl": ttl_minutes,
            "refresh_on_read": refresh_on_read,
        }

    logger.info(
        "Creating AsyncRedisSaver (ttl_minutes=%s, refresh_on_read=%s)",
        ttl_minutes,
        refresh_on_read,
    )
    return AsyncRedisSaver(**kwargs)


def create_fallback_checkpointer() -> MemorySaver:
    """In-memory checkpointer for dev/testing."""
    logger.info("Using MemorySaver (in-memory, non-persistent)")
    return MemorySaver()


# Backward compat: default singleton for dev/tests
checkpointer = MemorySaver()
