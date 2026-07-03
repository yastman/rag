"""Compatibility shim — retrieve node for legacy tests.

The original retrieve_node was removed with the legacy StateGraph stack.
This minimal implementation satisfies the latency-unit contract tests.
"""

from __future__ import annotations

import logging
import time
from typing import Any


logger = logging.getLogger(__name__)


async def retrieve_node(
    state: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    """Retrieve documents and record latency in seconds."""
    t0 = time.perf_counter()

    cache = getattr(runtime, "context", {}).get("cache") if hasattr(runtime, "context") else None
    embedding = state.get("query_embedding")

    documents = []

    if cache and hasattr(cache, "get_search_results"):
        try:
            documents = await cache.get_search_results(embedding) or []
        except Exception:
            logger.debug("retrieve_node cache lookup failed", exc_info=True)

    latency = time.perf_counter() - t0

    return {
        "documents": documents,
        "search_results_count": len(documents),
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": latency},
    }
