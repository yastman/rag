"""PipelineEventStream — Redis Streams event log for RAG pipeline observability.

Appends pipeline events (query, latency, cache hits, node timings) to a
Redis Stream for monitoring and debugging. Auto-trims to ~10000 entries.

Graceful degradation: all errors are caught and logged, never raising.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis.asyncio as redis


logger = logging.getLogger(__name__)

STREAM_KEY = "rag:pipeline:events"
STREAM_MAXLEN = 10_000


class PipelineEventStream:
    """Append-only event log backed by Redis Streams."""

    def __init__(self, redis_client: redis.Redis | None) -> None:
        self._redis = redis_client

    async def log_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> str | None:
        """Append an event to the pipeline stream.

        Args:
            event_type: Event category (e.g. "pipeline_result", "cache_hit").
            data: Arbitrary key-value payload. Values are coerced to str.

        Returns:
            Stream entry ID on success, None on failure or no Redis.
        """
        if not self._redis:
            return None

        fields: dict[str, str] = {
            "event_type": event_type,
            "timestamp": str(time.time()),
        }

        if data:
            for k, v in data.items():
                fields[k] = str(v)

        try:
            entry_id: str = await self._redis.xadd(
                STREAM_KEY,
                fields,
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
            logger.debug("event_stream: %s → %s", event_type, entry_id)
            return entry_id
        except Exception:
            logger.warning("event_stream: failed to log %s", event_type, exc_info=True)
            return None
