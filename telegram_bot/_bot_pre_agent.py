"""Pure pre-agent semantic-cache helpers extracted from ``bot.py`` (#1265).

Slice 1 PR-5 of the published bot.py decomposition plan.

Owns the four pre-agent helpers that prepare the semantic-cache check
and (on miss) the retrieval-vector state contract that the SDK agent
consumes downstream. The helpers are pure: stdlib (asyncio, time,
logging) only at module scope, plus a lazy import of
``telegram_bot.pipelines.state_contract`` inside
``_build_pre_agent_state_contract`` (the lazy import was already in the
original bot.py code and stays inside this module's function body).

Owned helpers (verbatim, byte-for-byte semantics with the pre-extract
``bot.py`` definitions; pinned by
``tests/contract/test_bot_pre_agent_extraction_contract.py``):

  - ``_build_pre_agent_state_contract`` — pre-agent miss state contract.
  - ``_has_async_method``               — duck-type async-method probe.
  - ``_get_or_compute_pre_agent_dense`` — cached/computed dense embedding.
  - ``_prepare_pre_agent_retrieval_vectors`` — sparse + ColBERT vector prep.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .pipelines.state_contract import PreAgentStateContract


logger = logging.getLogger(__name__)


def _build_pre_agent_state_contract(
    *,
    rag_result_store: dict[str, Any],
    query_type: str,
    topic_hint: str | None,
    dense_vector: list[float] | None,
    sparse_vector: dict[str, Any] | None,
    colbert_query: list[list[float]] | None,
    grounding_mode: str,
    filters: dict[str, Any] | None = None,
) -> PreAgentStateContract:
    """Build the shared pre-agent contract and preserve any upstream filters."""
    from .pipelines.state_contract import build_pre_agent_miss_contract

    resolved_filters = filters
    if resolved_filters is None:
        store_filters = rag_result_store.get("filters")
        resolved_filters = store_filters if isinstance(store_filters, dict) else None
    return build_pre_agent_miss_contract(
        query_type=query_type,
        topic_hint=topic_hint,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        grounding_mode=grounding_mode,
        filters=resolved_filters if isinstance(resolved_filters, dict) else None,
    )


def _has_async_method(obj: Any, name: str) -> bool:
    method = getattr(obj, name, None)
    return callable(method) and asyncio.iscoroutinefunction(method)


async def _get_or_compute_pre_agent_dense(
    cache: Any,
    embeddings: Any,
    query: str,
    result_store: dict[str, Any],
) -> list[float] | None:
    """Compute or retrieve cached dense embedding for semantic cache lookup.

    Uses ``aembed_dense_query`` when available, otherwise falls back to
    ``aembed_query``. Records ``pre_agent_embed_ms`` and optionally
    ``bge_model_processing_ms``.
    """
    dense: list[float] | None = await cache.get_embedding(query)
    if dense is not None:
        return dense

    embed_start = time.perf_counter()
    dense = None

    if _has_async_method(embeddings, "aembed_dense_query"):
        try:
            result: Any = await embeddings.aembed_dense_query(query)
            if isinstance(result, tuple) and len(result) == 2:
                dense = result[0]
                processing_s = result[1]
                if isinstance(processing_s, (int, float)):
                    result_store["bge_model_processing_ms"] = float(processing_s) * 1000
            else:
                dense = result
        except Exception:
            logger.warning("aembed_dense_query failed, falling back", exc_info=True)
            dense = None

    if dense is None and _has_async_method(embeddings, "aembed_query"):
        dense = await embeddings.aembed_query(query)

    if dense is not None:
        await cache.store_embedding(query, dense)

    result_store["pre_agent_embed_ms"] = (time.perf_counter() - embed_start) * 1000
    return dense


async def _prepare_pre_agent_retrieval_vectors(
    cache: Any,
    embeddings: Any,
    query: str,
    dense: list[float] | None,
    result_store: dict[str, Any],
) -> None:
    """Prepare sparse and ColBERT vectors after semantic cache MISS.

    Reads cached sparse, falls back to ``aembed_hybrid_with_colbert`` or
    ``aembed_hybrid``, and then standalone ``aembed_colbert_query`` when
    needed. Stashes ``cache_key_embedding``, ``cache_key_sparse``,
    ``cache_key_colbert``, and ``pre_agent_retrieval_vector_ms``.
    """
    prep_start = time.perf_counter()

    sparse = await cache.get_sparse_embedding(query)
    colbert = None

    if sparse is None:
        if _has_async_method(embeddings, "aembed_hybrid_with_colbert"):
            try:
                _, sparse, colbert = await embeddings.aembed_hybrid_with_colbert(query)
                if sparse is not None:
                    await cache.store_sparse_embedding(query, sparse)
            except Exception:
                logger.debug("Pre-agent hybrid ColBERT encode failed, skipping", exc_info=True)
                sparse = None
                colbert = None
        elif _has_async_method(embeddings, "aembed_hybrid"):
            try:
                _, sparse = await embeddings.aembed_hybrid(query)
                if sparse is not None:
                    await cache.store_sparse_embedding(query, sparse)
            except Exception:
                logger.debug("Pre-agent hybrid encode failed, skipping", exc_info=True)
                sparse = None

    if colbert is None and _has_async_method(embeddings, "aembed_colbert_query"):
        try:
            colbert = await embeddings.aembed_colbert_query(query)
        except Exception:
            logger.debug("Pre-agent ColBERT encode failed, skipping", exc_info=True)
            colbert = None

    result_store["cache_key_embedding"] = dense
    result_store["cache_key_sparse"] = sparse
    result_store["cache_key_colbert"] = colbert
    result_store["pre_agent_retrieval_vector_ms"] = (time.perf_counter() - prep_start) * 1000
