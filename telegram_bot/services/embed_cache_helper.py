"""Embedding + cache store helper for the client pipeline.

Encapsulates the embed→store→return flow with fire-and-forget background tasks
for Redis writes, saving ~10ms per query (2 Redis round-trips un-blocked).

Usage::

    result = await embed_and_store(text=user_text, cache=cache, embeddings=embeddings)
    dense = result["dense"]
    sparse = result["sparse"]
    colbert = result["colbert"]  # None if embeddings service doesn't support it
    hit = result["from_cache"]

Design (issue #954):
    - ``cache.store_embedding`` and ``cache.store_sparse_embedding`` are
      fire-and-forget; their results are never needed before the semantic
      cache check.  We use ``asyncio.create_task()`` so the event loop can
      schedule them in the background while the pipeline continues.
    - Task references are kept in a module-level set (``_bg_tasks``) to prevent
      garbage collection before completion (Python docs pattern for fire-and-forget).
    - Failures in store tasks are logged at DEBUG level and never raise.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any


logger = logging.getLogger(__name__)

# Module-level set keeps strong references to background tasks so the GC does
# not discard them before they finish (recommended pattern from Python docs).
_bg_tasks: set[asyncio.Task[None]] = set()


def _fire(coro: Any, label: str) -> None:
    """Create a background task and hold a strong reference until it completes."""
    task: asyncio.Task[None] = asyncio.create_task(
        _safe_store(coro, label), name=f"embed_cache_store:{label}"
    )
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _safe_store(coro: Any, label: str) -> None:
    """Run a store coroutine, logging any exception without raising."""
    try:
        await coro
    except Exception:
        logger.debug("Background cache store failed (%s)", label, exc_info=True)


async def embed_and_store(
    *,
    text: str,
    cache: Any,
    embeddings: Any,
) -> dict[str, Any]:
    """Embed *text* (or retrieve from cache) and fire cache stores as background tasks.

    Steps:
        1. Check Redis embedding cache for dense vector.
        2a. Cache HIT (both dense + sparse present): return immediately, no stores.
        2b. Cache MISS (dense missing): call ``aembed_hybrid_with_colbert`` (preferred)
            or ``aembed_hybrid`` or ``aembed_query`` and fire both store calls as
            background tasks via ``asyncio.create_task()``.
        2c. Partial cache (dense cached, sparse missing): re-embed to get sparse,
            fire only ``store_sparse_embedding`` as background task.

    Args:
        text: Query string to embed.
        cache: CacheLayerManager instance (must expose ``get_embedding``,
            ``get_sparse_embedding``, ``store_embedding``,
            ``store_sparse_embedding``).
        embeddings: Embeddings service (BGEM3HybridEmbeddings or compatible).

    Returns:
        Dict with keys:
            ``dense``      – list[float] dense vector
            ``sparse``     – dict sparse vector (or None if not available)
            ``colbert``    – list of ColBERT token vectors (or None)
            ``from_cache`` – True if both dense+sparse were served from cache
    """
    dense: list[float] | None = await cache.get_embedding(text)
    sparse: dict | None = await cache.get_sparse_embedding(text)
    colbert: list | None = None

    if dense is not None and sparse is not None:
        # Full cache hit — nothing to compute or store.
        return {
            "dense": dense,
            "sparse": sparse,
            "colbert": colbert,
            "from_cache": True,
        }

    _has_hybrid_colbert = asyncio.iscoroutinefunction(
        getattr(embeddings, "aembed_hybrid_with_colbert", None)
    )
    _has_hybrid = asyncio.iscoroutinefunction(getattr(embeddings, "aembed_hybrid", None))

    if dense is None:
        # Full miss — need to compute everything.
        if _has_hybrid_colbert:
            dense, sparse, colbert = await embeddings.aembed_hybrid_with_colbert(text)
            _fire(cache.store_embedding(text, dense), "store_embedding")
            _fire(cache.store_sparse_embedding(text, sparse), "store_sparse_embedding")
        elif _has_hybrid:
            dense, sparse = await embeddings.aembed_hybrid(text)
            _fire(cache.store_embedding(text, dense), "store_embedding")
            _fire(cache.store_sparse_embedding(text, sparse), "store_sparse_embedding")
        else:
            dense = await embeddings.aembed_query(text)
            _fire(cache.store_embedding(text, dense), "store_embedding")
    else:
        # Partial miss — dense cached but sparse expired (#637).
        if _has_hybrid_colbert:
            _, sparse, colbert = await embeddings.aembed_hybrid_with_colbert(text)
            _fire(cache.store_sparse_embedding(text, sparse), "store_sparse_embedding")
        elif _has_hybrid:
            _, sparse = await embeddings.aembed_hybrid(text)
            _fire(cache.store_sparse_embedding(text, sparse), "store_sparse_embedding")

    return {
        "dense": dense,
        "sparse": sparse,
        "colbert": colbert,
        "from_cache": False,
    }
