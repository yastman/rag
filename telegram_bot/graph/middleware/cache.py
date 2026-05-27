"""SemanticCacheMiddleware — SDK-native cache_check + cache_store hooks.

This is the ``create_agent``-compatible counterpart of the legacy graph
nodes :func:`telegram_bot.graph.nodes.cache.cache_check_node` and
:func:`telegram_bot.graph.nodes.cache.cache_store_node`. Slice 2 of the
voice-path migration plan in ADR-0010 (parent #1535 / #2051).

Behaviour
---------

* :py:meth:`before_agent` — runs once at the start of an agent invocation:
    1. Reads the latest human message text.
    2. If ``query_type`` is in :data:`~telegram_bot.services.rag_core.CACHEABLE_QUERY_TYPES`,
       computes (or reuses) the dense embedding via
       :func:`~telegram_bot.services.rag_core.compute_query_embedding`.
    3. Skips the lookup for contextual queries and for filter-sensitive
       queries that arrive without a resolved ``filter_signature``
       (matches the safety carve-out from ``cache_check_node``).
    4. Otherwise calls
       :func:`~telegram_bot.services.rag_core.check_semantic_cache`.
       On HIT, returns ``{"messages": [AIMessage(cached)], "jump_to": "end",
       "cache_hit": True, ...}`` so the SDK skips the model + tools loop
       entirely.
    5. On MISS, returns the fresh embedding / ColBERT vectors so
       downstream tools can reuse them without recomputation.

* :py:meth:`after_agent` — runs once after the agent finishes:
    1. Reads the final assistant response from
       ``state["messages"][-1].content``.
    2. Builds the same cacheability decision as
       :func:`cache_store_node` via
       :func:`telegram_bot.services.cache_policy.build_cacheability_decision`.
    3. Calls
       :func:`telegram_bot.services.cache_policy.maybe_store_semantic_response`
       to persist the response when the decision is favourable.

Dependency injection
--------------------

``cache`` and ``embeddings`` are passed via the constructor rather than
read from ``runtime.context``. The legacy node reads
``runtime.context["cache"]`` / ``runtime.context["embeddings"]``; the
middleware-shaped equivalent decouples the two so the class is unit
testable in isolation. Slice 3's ``create_voice_agent`` factory wires
the dependencies in at construction time.

Module-scope imports are constrained by
``tests/contract/test_voice_cache_middleware_contract.py``: stdlib +
``langchain.agents.middleware`` + ``langchain.messages`` +
``langgraph.runtime``. Heavy services
(``telegram_bot.services.rag_core`` etc.) are imported at module scope
because they are pure Python with no aiogram / qdrant_client / fastapi
imports themselves.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage
from langgraph.runtime import Runtime

from telegram_bot.observability import get_client
from telegram_bot.services.cache_policy import (
    SEMANTIC_CACHE_SCHEMA_VERSION,
    build_cacheability_decision,
    is_contextual_query,
    maybe_store_semantic_response,
    resolve_semantic_cache_signature,
)
from telegram_bot.services.query_filter_signal import detect_filter_sensitive_query
from telegram_bot.services.rag_core import (
    CACHEABLE_QUERY_TYPES,
    check_semantic_cache,
    compute_query_embedding,
)


logger = logging.getLogger(__name__)

# Default query type when the agent state has not been classified yet. Mirrors
# the fallback in cache_check_node so HIT/MISS semantics are identical.
_DEFAULT_QUERY_TYPE = "GENERAL"


class _CacheAwareState(AgentState):
    """``AgentState`` extension covering the cache fields the hooks read/write.

    All fields are :class:`typing_extensions.NotRequired` so old
    checkpoints that pre-date the cache middleware still validate. The
    schema is intentionally narrower than the eventual ``VoiceAgentState``
    (Slice 3) — Slice 2 only ships what the cache middleware itself
    exchanges with downstream middleware/tools.
    """

    query_type: NotRequired[str]
    cache_hit: NotRequired[bool]
    cached_response: NotRequired[str | None]
    query_embedding: NotRequired[list[float] | None]
    embeddings_cache_hit: NotRequired[bool]
    embedding_error: NotRequired[bool]
    embedding_error_type: NotRequired[str | None]
    colbert_query: NotRequired[list[list[float]] | None]
    filters: NotRequired[dict[str, Any]]
    semantic_cache_filter_signature: NotRequired[str | None]
    grounding_mode: NotRequired[str]
    grade_confidence: NotRequired[float]
    documents: NotRequired[list[Any]]
    search_results_count: NotRequired[int]
    response: NotRequired[str]
    latency_stages: NotRequired[dict[str, float]]


def _extract_query_text(state: AgentState | dict[str, Any]) -> str:
    """Return the latest human message content; tolerant of dict/AIMessage."""
    messages = state.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content", "")
    return content or ""


def _resolve_filter_signature(
    state: dict[str, Any] | AgentState, query: str
) -> tuple[bool, str | None]:
    """Mirror ``_resolve_graph_filter_signature`` from the legacy node."""
    filter_sensitive = detect_filter_sensitive_query(query).is_filter_sensitive
    filter_signature = resolve_semantic_cache_signature(
        filters=state.get("filters"),
        explicit_signature=state.get("semantic_cache_filter_signature"),
    )
    return filter_sensitive, filter_signature


def _final_response_text(state: AgentState | dict[str, Any]) -> str:
    """Return the latest assistant message content, falling back to ``response``."""
    messages = state.get("messages") or []
    for message in reversed(messages):
        message_type = getattr(message, "type", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if message_type in {"ai", "assistant"}:
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content", "")
            if content:
                return content
    fallback = state.get("response") if isinstance(state, dict) else None
    return fallback or ""


class SemanticCacheMiddleware(AgentMiddleware):
    """Skip the agent loop on semantic-cache HIT and persist on MISS.

    Args:
        cache: Cache layer manager exposing ``check_semantic`` (and the
            shape :func:`check_semantic_cache` expects).
        embeddings: Embedder exposing ``aembed_query`` (and optionally
            ``aembed_colbert_query`` for ColBERT prep on MISS).
        cache_scope: Cache namespace; ``"rag"`` matches the voice graph.
        agent_role: Role tag for cache key isolation. Voice path historically
            shares responses across roles, so the default is ``None``.
    """

    state_schema = _CacheAwareState

    def __init__(
        self,
        *,
        cache: Any,
        embeddings: Any,
        cache_scope: str = "rag",
        agent_role: str | None = None,
    ) -> None:
        super().__init__()
        self.cache = cache
        self.embeddings = embeddings
        self.cache_scope = cache_scope
        self.agent_role = agent_role

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self,
        state: _CacheAwareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Cache-check hook; short-circuits the agent loop on HIT."""
        query = _extract_query_text(state)
        if not query:
            return None
        query_type = state.get("query_type") or _DEFAULT_QUERY_TYPE
        if query_type not in CACHEABLE_QUERY_TYPES:
            # Non-cacheable query types skip the cache layer entirely so we do
            # not pay the embedding cost on chit-chat / off-topic flows. This
            # matches the ``cache_check_node`` behaviour where the legacy
            # graph routes those types past cache_check via classify_node.
            return None

        lf = get_client()
        try:
            lf.update_current_span(
                input={
                    "query_preview": query[:120],
                    "query_len": len(query),
                    "query_hash": hashlib.sha256(query.encode()).hexdigest()[:8],
                    "query_type": query_type,
                }
            )
        except Exception:  # pragma: no cover — observability must never raise
            logger.debug("update_current_span (cache before) failed", exc_info=True)

        start = time.perf_counter()

        try:
            embedding, _sparse, colbert_query, embeddings_cache_hit = await compute_query_embedding(
                query, cache=self.cache, embeddings=self.embeddings
            )
        except Exception as exc:
            embedding_error_type = type(exc).__name__
            logger.error("Cache middleware embedding failed: %s: %s", embedding_error_type, exc)
            latency = time.perf_counter() - start
            try:
                lf.update_current_span(
                    level="ERROR",
                    output={
                        "embedding_error": True,
                        "embedding_error_type": embedding_error_type,
                        "duration_ms": round(latency * 1000, 1),
                    },
                )
            except Exception:  # pragma: no cover
                logger.debug("update_current_span (cache embed-error) failed", exc_info=True)
            # On embedding failure we surface the graceful fallback message
            # the legacy node returned and still short-circuit, so no half
            # answer leaks through. Mirrors lines 89–106 of cache.py.
            return {
                "messages": [
                    AIMessage(
                        content="Сервис временно недоступен. Пожалуйста, повторите через минуту."
                    )
                ],
                "jump_to": "end",
                "cache_hit": False,
                "cached_response": None,
                "query_embedding": None,
                "embeddings_cache_hit": False,
                "embedding_error": True,
                "embedding_error_type": embedding_error_type,
                "latency_stages": {
                    **(state.get("latency_stages") or {}),
                    "cache_check": latency,
                },
            }

        filter_sensitive, filter_signature = _resolve_filter_signature(state, query)
        contextual_query = is_contextual_query(query)
        if contextual_query or (filter_sensitive and filter_signature is None):
            hit, cached = False, None
        else:
            hit, cached = await check_semantic_cache(
                query,
                embedding,
                query_type,
                cache=self.cache,
                agent_role=self.agent_role,
                filter_signature=filter_signature,
            )

        latency = time.perf_counter() - start

        if hit:
            logger.info("cache_middleware HIT (%.3fs, type=%s)", latency, query_type)
            try:
                lf.update_current_span(
                    output={
                        "cache_hit": True,
                        "embeddings_cache_hit": embeddings_cache_hit,
                        "hit_layer": "semantic",
                        "duration_ms": round(latency * 1000, 1),
                    }
                )
            except Exception:  # pragma: no cover
                logger.debug("update_current_span (cache HIT) failed", exc_info=True)
            return {
                "messages": [AIMessage(content=cached or "")],
                "jump_to": "end",
                "cache_hit": True,
                "cached_response": cached,
                "query_embedding": embedding,
                "embeddings_cache_hit": embeddings_cache_hit,
                "embedding_error": False,
                "embedding_error_type": None,
                "colbert_query": None,
                "response": cached or "",
                "latency_stages": {
                    **(state.get("latency_stages") or {}),
                    "cache_check": latency,
                },
            }

        # MISS: surface vectors so downstream tools reuse them. Match the
        # legacy ``cache_check_node`` MISS shape, including the ColBERT
        # fallback for embedders that expose ``aembed_colbert_query`` as a
        # standalone async method (older bundle implementations).
        if colbert_query is None:
            colbert_only = getattr(self.embeddings, "aembed_colbert_query", None)
            if callable(colbert_only):
                try:
                    colbert_query = await colbert_only(query)
                except Exception:
                    logger.debug(
                        "ColBERT query encode failed (non-critical), skipping",
                        exc_info=True,
                    )

        logger.info("cache_middleware MISS (%.3fs, type=%s)", latency, query_type)
        try:
            lf.update_current_span(
                output={
                    "cache_hit": False,
                    "embeddings_cache_hit": embeddings_cache_hit,
                    "hit_layer": "none",
                    "duration_ms": round(latency * 1000, 1),
                }
            )
        except Exception:  # pragma: no cover
            logger.debug("update_current_span (cache MISS) failed", exc_info=True)
        return {
            "cache_hit": False,
            "cached_response": None,
            "query_embedding": embedding,
            "embeddings_cache_hit": embeddings_cache_hit,
            "embedding_error": False,
            "embedding_error_type": None,
            "colbert_query": colbert_query,
            "latency_stages": {
                **(state.get("latency_stages") or {}),
                "cache_check": latency,
            },
        }

    async def aafter_agent(
        self,
        state: _CacheAwareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Persist the agent's final response into the semantic cache."""
        # Cache HITs already routed through abefore_agent's jump_to=end and
        # left the response in place; we must not store the cached response
        # back as a fresh entry (would race with TTL bookkeeping).
        if state.get("cache_hit"):
            return None

        query = _extract_query_text(state)
        if not query:
            return None
        response = _final_response_text(state)
        if not response:
            return None
        embedding = state.get("query_embedding")
        if not embedding:
            return None
        query_type = state.get("query_type") or _DEFAULT_QUERY_TYPE
        if query_type not in CACHEABLE_QUERY_TYPES:
            return None

        filter_sensitive, filter_signature = _resolve_filter_signature(state, query)
        if filter_sensitive and filter_signature is None:
            # Filter-sensitive query without a resolved signature: storing
            # would cross-contaminate filter buckets. Skip just like the
            # legacy ``cache_store_node``.
            return None

        decision = build_cacheability_decision(
            result=dict(state),
            query_type=query_type,
            grounding_mode=str(state.get("grounding_mode") or "normal"),
            documents=state.get("documents") or [],
            cache_hit=False,
            contextual=is_contextual_query(query),
            grade_confidence=float(state.get("grade_confidence") or 0.0),
            confidence_threshold=0.0,
            schema_version=SEMANTIC_CACHE_SCHEMA_VERSION,
        )

        stored = False
        try:
            stored = await maybe_store_semantic_response(
                cache=self.cache,
                query=query,
                response=response,
                vector=embedding,
                query_type=query_type,
                cache_scope=self.cache_scope,
                decision=decision,
                agent_role=self.agent_role,
                filter_signature=filter_signature,
            )
        except Exception as exc:
            # Match the legacy node: a cache-store failure must never
            # destroy the response. Log + swallow + continue.
            logger.warning(
                "cache_middleware: semantic store failed, response preserved: %s: %s",
                type(exc).__name__,
                exc,
            )

        try:
            get_client().update_current_span(output={"stored": stored, "stored_semantic": stored})
        except Exception:  # pragma: no cover
            logger.debug("update_current_span (cache_store) failed", exc_info=True)

        # Surface the same observability fields the legacy node wrote into
        # the state so ``_handle_query_supervisor``'s post-processing block
        # keeps working unchanged.
        return {
            "response": response,
            "response_state": decision.response_state,
            "degraded_reason": decision.degraded_reason,
            "cache_eligible": decision.cache_eligible,
            "store_reason": decision.store_reason,
        }


__all__ = ("SemanticCacheMiddleware", "_CacheAwareState")
