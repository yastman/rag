# SPDX-License-Identifier: MIT
"""Query rewrite and cache-store pipeline stages."""

from __future__ import annotations

import logging
import time
from typing import Any

from src.retrieval.topic_classifier import get_query_topic_hint
from src.runtime.services.cache_policy import (
    SEMANTIC_CACHE_SCHEMA_VERSION,
    build_cacheability_decision,
    is_contextual_query,
    maybe_store_semantic_response,
)
from src.runtime.services.query_preprocessor import expand_short_query
from src.runtime.services.rag_core import rewrite_query_via_llm


logger = logging.getLogger(__name__)


def _graph_config_from_env() -> Any:
    from src.runtime.config import GraphConfig

    return GraphConfig.from_env()


def _cacheable_query_types() -> set[str]:
    from src.runtime.services.rag_core import CACHEABLE_QUERY_TYPES

    return set(CACHEABLE_QUERY_TYPES)


# ---------------------------------------------------------------------------
# Step 5: Rewrite query
# ---------------------------------------------------------------------------


async def _rewrite_query(
    query: str,
    rewrite_count: int,
    *,
    llm: Any | None = None,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rewrite user query for better retrieval.

    Returns dict with rewritten_query, rewrite_count, rewrite_effective, and latency.
    """
    t0 = time.perf_counter()
    topic_hint = get_query_topic_hint(query)
    expanded_query = expand_short_query(
        query,
        topic_hint=topic_hint.value if topic_hint is not None else None,
    )
    if expanded_query != query:
        elapsed = time.perf_counter() - t0
        logger.info(
            "rewrite: deterministic expansion '%s' → '%s' (%.3fs)",
            query,
            expanded_query,
            elapsed,
        )
        return {
            "rewritten_query": expanded_query,
            "rewrite_count": rewrite_count + 1,
            "rewrite_effective": True,
            "rewrite_provider_model": "deterministic_short_query_expansion",
            "latency_stages": {**latency_stages, "rewrite": elapsed},
        }

    try:
        config = _graph_config_from_env()
        if llm is None:
            llm = config.create_llm()
        rewritten, effective, rewrite_actual_model = await rewrite_query_via_llm(query, llm=llm)
    except Exception:
        logger.exception("rewrite: LLM rewrite failed, keeping original query")
        rewritten = query
        effective = False
        rewrite_actual_model = "fallback"

    elapsed = time.perf_counter() - t0
    logger.info(
        "rewrite: attempt %d, '%.50s' → '%.50s' (%.3fs)",
        rewrite_count + 1,
        query,
        rewritten,
        elapsed,
    )

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count + 1,
        "rewrite_effective": effective,
        "rewrite_provider_model": rewrite_actual_model,
        "latency_stages": {**latency_stages, "rewrite": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 6: Cache store
# ---------------------------------------------------------------------------


async def _cache_store(
    query: str,
    response: str,
    query_embedding: list[float] | None,
    query_type: str,
    user_id: int,
    *,
    cache: Any,
    search_results_count: int = 0,
    latency_stages: dict[str, float],
    agent_role: str | None = None,
) -> dict[str, Any]:
    """Store response in semantic cache (allowlisted types only).

    Returns dict with latency update.
    """
    start = time.perf_counter()

    stored_semantic = False
    if response and query_embedding and query_type in _cacheable_query_types():
        # Legacy helper kept as a thin delegate so tests and older callsites do not
        # carry a second cache-policy implementation.
        decision = build_cacheability_decision(
            result={
                "response": response,
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "fallback_used": False,
                "safe_fallback_used": False,
                "llm_provider_model": "",
                "llm_timeout": False,
            },
            query_type=query_type,
            grounding_mode="normal",
            documents=[{"text": response}],
            cache_hit=False,
            contextual=is_contextual_query(query),
            grade_confidence=1.0,
            confidence_threshold=0.0,
            schema_version=SEMANTIC_CACHE_SCHEMA_VERSION,
        )
        try:
            stored_semantic = await maybe_store_semantic_response(
                cache=cache,
                query=query,
                response=response,
                vector=query_embedding,
                query_type=query_type,
                cache_scope="rag",
                decision=decision,
                agent_role=agent_role,
            )
        except Exception as exc:
            # RedisVLError, RedisSearchError, SchemaValidationError, or any unexpected
            # error from store_semantic must never lose the response (#524).
            logger.warning(
                "cache_store: semantic store failed, response preserved: %s: %s",
                type(exc).__name__,
                exc,
            )

        if stored_semantic:
            logger.info("cache_store: stored=semantic (type=%s)", query_type)

    latency = time.perf_counter() - start

    return {
        "stored_semantic": stored_semantic,
        "latency_stages": {**latency_stages, "cache_store": latency},
    }
