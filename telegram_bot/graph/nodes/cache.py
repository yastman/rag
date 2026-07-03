"""Compatibility shim — cache check node for legacy tests.

The original cache_check_node was removed with the legacy StateGraph stack.
This minimal implementation satisfies the latency-unit contract tests.
"""

from __future__ import annotations

import logging
import time
from typing import Any


logger = logging.getLogger(__name__)


async def cache_check_node(
    state: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    """Check semantic cache and record latency in seconds."""
    t0 = time.perf_counter()

    query = state.get("query", "")

    cache = getattr(runtime, "context", {}).get("cache") if hasattr(runtime, "context") else None
    embeddings = (
        getattr(runtime, "context", {}).get("embeddings") if hasattr(runtime, "context") else None
    )

    embedding = None
    cache_hit = False
    cached_response = None

    if cache and embeddings and query:
        try:
            embedding = (
                await cache.get_embedding(query) if hasattr(cache, "get_embedding") else None
            )
            if embedding is None and hasattr(embeddings, "aembed_query"):
                embedding = await embeddings.aembed_query(query)
        except Exception:
            logger.debug("cache_check_node embedding failed", exc_info=True)

        if embedding and hasattr(cache, "check_semantic"):
            try:
                cached_response = await cache.check_semantic(query)
                cache_hit = cached_response is not None
            except Exception:
                logger.debug("cache_check_node cache check failed", exc_info=True)

    latency = time.perf_counter() - t0

    return {
        "cache_hit": cache_hit,
        "cached_response": cached_response,
        "query_embedding": embedding,
        "latency_stages": {**state.get("latency_stages", {}), "cache_check": latency},
    }
