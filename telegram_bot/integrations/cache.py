"""CacheLayerManager — 5-tier Redis cache for RAG pipeline.

Replaces CacheService (1000+ LOC) with a focused ~300 LOC implementation.

Tiers:
  1. Semantic cache (RedisVL SemanticCache, threshold per query_type)
  2. Embeddings cache (Redis exact, 7d TTL)
  3. Sparse embeddings cache (Redis exact, 7d TTL)
  4. Search results cache (Redis exact, 2h TTL)
  5. Rerank results cache (Redis exact, 2h TTL)
  + Conversation history (Redis LIST, 20 msgs, 2h TTL)

NOTE: redisvl imports are lazy-loaded in initialize() to avoid ~7.5s import
overhead from voyageai SDK (pandas, scipy.stats) during test collection.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

import redis.asyncio as redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

from telegram_bot.observability import get_client, observe


if TYPE_CHECKING:
    from redisvl.extensions.cache.embeddings import EmbeddingsCache
    from redisvl.extensions.cache.llm import SemanticCache

logger = logging.getLogger(__name__)

CACHE_VERSION = "v5"
SEMANTIC_CACHE_VERSION = "v6"

# Default TTLs per exact-cache tier (seconds)
DEFAULT_TTLS: dict[str, int] = {
    "embeddings": 7 * 86400,  # 7 days
    "sparse": 7 * 86400,  # 7 days
    "search": 7200,  # 2 hours
    "rerank": 7200,  # 2 hours
}

_METRIC_TIERS = ("semantic", "embeddings", "sparse", "search", "rerank")


def _hash(data: str) -> str:
    """SHA256 hash truncated to 16 chars for cache keys."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _normalize_query_for_cache(text: str) -> str:
    """Normalize query for cache key: lowercase, strip whitespace and trailing punctuation.

    Ensures 'ВНЖ?' and 'внж' produce the same embedding/sparse cache key,
    avoiding duplicate API calls for semantically identical queries.
    Applied ONLY to cache key generation, not to the query in the pipeline.
    """
    return re.sub(r"[^\w\s]+$", "", text.strip().lower()).strip()


def _create_semantic_cache(
    redis_url: str,
    distance_threshold: float,
    ttl: int,
    vectorizer: Any,
) -> SemanticCache | None:
    """Create RedisVL SemanticCache instance. Returns None on failure."""
    try:
        from redisvl.extensions.cache.llm import SemanticCache

        cache = SemanticCache(
            name=f"sem:{SEMANTIC_CACHE_VERSION}:bge1024",
            redis_url=redis_url,
            ttl=ttl,
            distance_threshold=distance_threshold,
            vectorizer=vectorizer,
            filterable_fields=[
                {"name": "query_type", "type": "tag"},
                {"name": "language", "type": "tag"},
                {"name": "user_id", "type": "tag"},
                {"name": "cache_scope", "type": "tag"},
                {"name": "agent_role", "type": "tag"},
                {"name": "grounding_mode", "type": "tag"},
                {"name": "semantic_cache_safe_reuse", "type": "tag"},
            ],
        )
        logger.info("SemanticCache initialized (threshold=%.2f, ttl=%ds)", distance_threshold, ttl)
        return cache
    except Exception as e:
        logger.warning("SemanticCache init failed: %s: %s", type(e).__name__, e)
        return None


def _create_embed_cache(
    async_redis_client: Any,
    ttl: int,
) -> EmbeddingsCache | None:
    """Create RedisVL EmbeddingsCache instance. Returns None on failure."""
    try:
        from redisvl.extensions.cache.embeddings import EmbeddingsCache

        cache = EmbeddingsCache(
            name=f"embeddings:{CACHE_VERSION}",
            ttl=ttl,
            async_redis_client=async_redis_client,
        )
        logger.info("EmbeddingsCache initialized (ttl=%ds)", ttl)
        return cache
    except Exception as e:
        logger.warning("EmbeddingsCache init failed: %s: %s", type(e).__name__, e)
        return None


class CacheLayerManager:
    """5-tier Redis cache manager for RAG pipeline."""

    def __init__(
        self,
        redis_url: str,
        cache_thresholds: dict[str, float] | None = None,
        cache_ttl: dict[str, int] | None = None,
        exact_ttls: dict[str, int] | None = None,
        conversation_max_messages: int = 20,
        conversation_ttl: int = 7200,
    ) -> None:
        self.redis_url = redis_url
        self.redis: redis.Redis | None = None
        self.semantic_cache: SemanticCache | None = None
        self.embed_cache: EmbeddingsCache | None = None

        # Semantic cache thresholds per query type (cosine distance, lower = stricter)
        self.cache_thresholds = cache_thresholds or {
            "FAQ": 0.12,
            "ENTITY": 0.10,
            "GENERAL": 0.08,
            "STRUCTURED": 0.05,
        }

        # Semantic cache TTL per query type (seconds)
        self.cache_ttl = cache_ttl or {
            "FAQ": 86400,  # 24h
            "ENTITY": 3600,  # 1h
            "GENERAL": 3600,  # 1h
            "STRUCTURED": 7200,  # 2h
        }

        # Exact cache TTLs
        self.exact_ttls = exact_ttls or dict(DEFAULT_TTLS)

        # Conversation settings
        self.conversation_max_messages = conversation_max_messages
        self.conversation_ttl = conversation_ttl

        # Metrics
        self._metrics: dict[str, dict[str, int]] = {
            tier: {"hits": 0, "misses": 0} for tier in _METRIC_TIERS
        }

    async def initialize(self) -> None:
        """Connect to Redis and set up semantic cache (lazy imports)."""
        try:
            self.redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                retry=Retry(ExponentialBackoff(), 3),
                health_check_interval=30,
            )
            await self.redis.ping()  # type: ignore[misc]
            logger.info("Redis connected: %s", self.redis_url)
        except Exception as e:
            logger.error("Redis connection failed: %s: %s", type(e).__name__, e)
            self.redis = None
            return

        # Lazy import vectorizer for semantic cache
        try:
            import os

            from telegram_bot.services.vectorizers import BgeM3CacheVectorizer

            bge_url = os.getenv("BGE_M3_URL", "http://bge-m3:8000")
            vectorizer = BgeM3CacheVectorizer(base_url=bge_url)

            default_threshold = self.cache_thresholds.get("GENERAL", 0.08)
            default_ttl = self.cache_ttl.get("GENERAL", 3600)
            self.semantic_cache = _create_semantic_cache(
                redis_url=self.redis_url,
                distance_threshold=default_threshold,
                ttl=default_ttl,
                vectorizer=vectorizer,
            )
        except Exception as e:
            logger.warning("Semantic cache setup skipped: %s: %s", type(e).__name__, e)
            self.semantic_cache = None

        # Init EmbeddingsCache (RedisVL SDK) for dense embedding storage
        try:
            embed_ttl = self.exact_ttls.get("embeddings", DEFAULT_TTLS["embeddings"])
            self.embed_cache = _create_embed_cache(
                async_redis_client=self.redis,
                ttl=embed_ttl,
            )
        except Exception as e:
            logger.warning("EmbeddingsCache setup skipped: %s: %s", type(e).__name__, e)
            self.embed_cache = None

    async def close(self) -> None:
        """Close all connections."""
        if self.semantic_cache:
            with contextlib.suppress(Exception):
                await self.semantic_cache.adisconnect()
        if self.redis:
            await self.redis.aclose()
        logger.info("CacheLayerManager closed")

    # ========== Semantic Cache ==========

    @observe(name="cache-semantic-check", capture_input=False, capture_output=False)
    async def check_semantic(
        self,
        query: str,
        vector: list[float],
        query_type: str,
        language: str = "ru",
        user_id: int | None = None,
        cache_scope: str | None = None,
        agent_role: str | None = None,
        grounding_mode: str | None = None,
        require_safe_reuse: bool = False,
        cache_timeout: float = 0.3,
    ) -> str | None:
        """Check semantic cache with query-type-specific threshold.

        Args:
            query: User query text (fallback if no vector)
            vector: Pre-computed dense embedding (BGE-M3 1024-dim)
            query_type: Query type for threshold selection
            language: Language filter
            user_id: User ID for per-user isolation (Tag filter)
            cache_scope: Scope tag for isolation (e.g. "rag", "history")
            agent_role: Role tag for isolation (e.g. "client", "manager")
            cache_timeout: Max wait time in seconds (default 0.3s)

        Returns:
            Cached response string, or None on miss/timeout
        """
        lf = get_client()
        lf.update_current_span(
            input={
                "query_type": query_type,
                "language": language,
                "has_user_id": user_id is not None,
                "has_cache_scope": cache_scope is not None,
                "has_agent_role": agent_role is not None,
                "grounding_mode": grounding_mode,
                "require_safe_reuse": require_safe_reuse,
                "cache_timeout_s": cache_timeout,
                "query_length": len(query),
                "vector_dim": len(vector),
            }
        )

        if not self.semantic_cache:
            lf.update_current_span(output={"hit": False, "semantic_cache_enabled": False})
            return None

        threshold = self.cache_thresholds.get(query_type, 0.08)

        try:
            from redisvl.query.filter import Tag

            filter_expr = (Tag("language") == language) & (Tag("query_type") == query_type)
            if user_id is not None:
                filter_expr = filter_expr & (Tag("user_id") == str(user_id))
            if cache_scope is not None:
                filter_expr = filter_expr & (Tag("cache_scope") == cache_scope)
            if agent_role is not None:
                filter_expr = filter_expr & (Tag("agent_role") == agent_role)
            if grounding_mode is not None:
                filter_expr = filter_expr & (Tag("grounding_mode") == grounding_mode)
            if require_safe_reuse:
                filter_expr = filter_expr & (Tag("semantic_cache_safe_reuse") == "true")
            start = time.time()

            try:
                results = await asyncio.wait_for(
                    self.semantic_cache.acheck(
                        vector=vector,
                        filter_expression=filter_expr,
                        num_results=1,
                        distance_threshold=threshold,
                    ),
                    timeout=cache_timeout,
                )
            except TimeoutError:
                latency_ms = (time.time() - start) * 1000
                logger.warning("Semantic cache timeout (%.0fms > %.1fs)", latency_ms, cache_timeout)
                self._metrics["semantic"]["misses"] += 1
                lf.update_current_span(
                    level="WARNING",
                    status_message="Semantic cache timeout",
                    output={"hit": False, "timeout": True, "latency_ms": round(latency_ms, 2)},
                )
                return None

            latency_ms = (time.time() - start) * 1000

            if results:
                self._metrics["semantic"]["hits"] += 1
                distance = results[0].get("vector_distance", 0)
                logger.info(
                    "Semantic HIT (%.0fms, dist=%.3f, threshold=%.2f, type=%s)",
                    latency_ms,
                    float(distance),
                    threshold,
                    query_type,
                )
                lf.update_current_span(
                    output={
                        "hit": True,
                        "latency_ms": round(latency_ms, 2),
                        "distance": float(distance),
                        "threshold": threshold,
                    }
                )
                return str(results[0].get("response", ""))

            self._metrics["semantic"]["misses"] += 1
            logger.debug("Semantic MISS (%.0fms, type=%s)", latency_ms, query_type)
            lf.update_current_span(
                output={"hit": False, "latency_ms": round(latency_ms, 2), "threshold": threshold}
            )
            return None

        except Exception as e:
            logger.error("Semantic cache error: %s: %s", type(e).__name__, e)
            self._metrics["semantic"]["misses"] += 1
            lf.update_current_span(
                level="ERROR",
                status_message=f"Semantic cache error: {type(e).__name__}",
                output={"hit": False, "error": type(e).__name__},
            )
            return None

    @observe(name="cache-semantic-store", capture_input=False, capture_output=False)
    async def store_semantic(
        self,
        query: str,
        response: str,
        vector: list[float],
        query_type: str,
        language: str = "ru",
        user_id: int | None = None,
        cache_scope: str | None = None,
        agent_role: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store query-response pair in semantic cache."""
        lf = get_client()
        lf.update_current_span(
            input={
                "query_type": query_type,
                "language": language,
                "has_user_id": user_id is not None,
                "has_cache_scope": cache_scope is not None,
                "has_agent_role": agent_role is not None,
                "metadata_keys": sorted((metadata or {}).keys()),
                "query_length": len(query),
                "response_length": len(response),
                "vector_dim": len(vector),
            }
        )
        if not self.semantic_cache:
            lf.update_current_span(output={"stored": False, "semantic_cache_enabled": False})
            return

        ttl = self.cache_ttl.get(query_type, 3600)
        filters: dict[str, str] = {"query_type": query_type, "language": language}
        if user_id is not None:
            filters["user_id"] = str(user_id)
        if cache_scope is not None:
            filters["cache_scope"] = cache_scope
        if agent_role is not None:
            filters["agent_role"] = agent_role
        if metadata:
            grounding_mode = metadata.get("grounding_mode")
            if isinstance(grounding_mode, str) and grounding_mode:
                filters["grounding_mode"] = grounding_mode
            if "semantic_cache_safe_reuse" in metadata:
                filters["semantic_cache_safe_reuse"] = str(
                    bool(metadata["semantic_cache_safe_reuse"])
                ).lower()
        try:
            await self.semantic_cache.astore(
                prompt=query,
                response=response,
                vector=vector,
                filters=filters,
                metadata=metadata,
                ttl=ttl,
            )
            logger.debug(
                "Stored semantic: %s... (type=%s, scope=%s, role=%s, ttl=%ds)",
                query[:50],
                query_type,
                cache_scope,
                agent_role,
                ttl,
            )
            lf.update_current_span(output={"stored": True, "ttl_s": ttl})
        except Exception as e:
            logger.error("Semantic store error: %s: %s", type(e).__name__, e)
            lf.update_current_span(
                level="ERROR",
                status_message=f"Semantic store error: {type(e).__name__}",
                output={"stored": False, "error": type(e).__name__},
            )

    # ========== Exact Caches (SET/GET) ==========

    @observe(name="cache-exact-get", capture_input=False, capture_output=False)
    async def get_exact(self, tier: str, key: str) -> Any | None:
        """Get value from exact cache tier.

        Args:
            tier: Cache tier name (embeddings, sparse, search, rerank)
            key: Cache key (pre-hashed or raw)

        Returns:
            Deserialized value, or None on miss
        """
        lf = get_client()
        lf.update_current_span(input={"tier": tier, "key_hash": key[:16]})
        if not self.redis:
            lf.update_current_span(output={"hit": False, "redis_enabled": False, "tier": tier})
            return None

        redis_key = f"{tier}:{CACHE_VERSION}:{key}"
        try:
            cached = await self.redis.get(redis_key)
            if cached:
                if tier in self._metrics:
                    self._metrics[tier]["hits"] += 1
                lf.update_current_span(output={"hit": True, "tier": tier})
                return json.loads(cached)
            if tier in self._metrics:
                self._metrics[tier]["misses"] += 1
            lf.update_current_span(output={"hit": False, "tier": tier})
            return None
        except Exception as e:
            logger.error("Cache get error (%s): %s: %s", tier, type(e).__name__, e)
            if tier in self._metrics:
                self._metrics[tier]["misses"] += 1
            lf.update_current_span(
                level="ERROR",
                status_message=f"Exact cache get error: {type(e).__name__}",
                output={"hit": False, "tier": tier, "error": type(e).__name__},
            )
            return None

    @observe(name="cache-exact-store", capture_input=False, capture_output=False)
    async def store_exact(self, tier: str, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value in exact cache tier.

        Args:
            tier: Cache tier name
            key: Cache key
            value: JSON-serializable value
            ttl: Optional TTL override (seconds)
        """
        effective_ttl = ttl or self.exact_ttls.get(tier, 3600)
        lf = get_client()
        lf.update_current_span(
            input={
                "tier": tier,
                "key_hash": key[:16],
                "ttl_s": effective_ttl,
            }
        )
        if not self.redis:
            lf.update_current_span(output={"stored": False, "redis_enabled": False, "tier": tier})
            return

        redis_key = f"{tier}:{CACHE_VERSION}:{key}"
        try:
            await self.redis.setex(redis_key, effective_ttl, json.dumps(value))
            lf.update_current_span(output={"stored": True, "tier": tier, "ttl_s": effective_ttl})
        except Exception as e:
            logger.error("Cache store error (%s): %s: %s", tier, type(e).__name__, e)
            lf.update_current_span(
                level="ERROR",
                status_message=f"Exact cache store error: {type(e).__name__}",
                output={"stored": False, "tier": tier, "error": type(e).__name__},
            )

    # ========== Convenience: Embeddings ==========

    @observe(name="cache-embedding-get", capture_input=False, capture_output=False)
    async def get_embedding(self, text: str, model: str = "bge-m3") -> list[float] | None:
        """Get cached dense embedding via RedisVL EmbeddingsCache."""
        lf = get_client()
        lf.update_current_span(input={"model": model, "text_length": len(text)})
        if self.embed_cache is None:
            lf.update_current_span(output={"hit": False, "embed_cache_enabled": False})
            return None
        try:
            normalized = _normalize_query_for_cache(text)
            result = await self.embed_cache.aget(content=normalized, model_name=model)
            if result is not None:
                self._metrics["embeddings"]["hits"] += 1
                lf.update_current_span(output={"hit": True})
                return list(result["embedding"])
            self._metrics["embeddings"]["misses"] += 1
            lf.update_current_span(output={"hit": False})
            return None
        except Exception as e:
            logger.error("EmbeddingsCache get error: %s: %s", type(e).__name__, e)
            self._metrics["embeddings"]["misses"] += 1
            lf.update_current_span(
                level="ERROR",
                status_message=f"EmbeddingsCache get error: {type(e).__name__}",
                output={"hit": False, "error": type(e).__name__},
            )
            return None

    @observe(name="cache-embedding-store", capture_input=False, capture_output=False)
    async def store_embedding(
        self, text: str, embedding: list[float], model: str = "bge-m3"
    ) -> None:
        """Store dense embedding via RedisVL EmbeddingsCache."""
        lf = get_client()
        lf.update_current_span(
            input={"model": model, "text_length": len(text), "embedding_dim": len(embedding)}
        )
        if self.embed_cache is None:
            lf.update_current_span(output={"stored": False, "embed_cache_enabled": False})
            return
        try:
            normalized = _normalize_query_for_cache(text)
            ttl = self.exact_ttls.get("embeddings")
            await self.embed_cache.aset(
                content=normalized,
                model_name=model,
                embedding=embedding,
                ttl=ttl,
            )
            lf.update_current_span(output={"stored": True})
        except Exception as e:
            logger.error("EmbeddingsCache store error: %s: %s", type(e).__name__, e)
            lf.update_current_span(
                level="ERROR",
                status_message=f"EmbeddingsCache store error: {type(e).__name__}",
                output={"stored": False, "error": type(e).__name__},
            )

    # ========== Convenience: Sparse Embeddings ==========

    @observe(name="cache-sparse-get", capture_input=False, capture_output=False)
    async def get_sparse_embedding(
        self, text: str, model: str = "bge_m3_sparse"
    ) -> dict[str, Any] | None:
        """Get cached sparse embedding."""
        lf = get_client()
        lf.update_current_span(input={"model": model, "text_length": len(text)})
        result = await self.get_exact(
            "sparse", _hash(f"{model}:{_normalize_query_for_cache(text)}")
        )
        lf.update_current_span(output={"hit": result is not None})
        return result

    @observe(name="cache-sparse-store", capture_input=False, capture_output=False)
    async def store_sparse_embedding(
        self, text: str, sparse_vector: dict[str, Any], model: str = "bge_m3_sparse"
    ) -> None:
        """Store sparse embedding."""
        lf = get_client()
        lf.update_current_span(
            input={
                "model": model,
                "text_length": len(text),
                "sparse_indices_count": len(sparse_vector.get("indices", [])),
            }
        )
        await self.store_exact(
            "sparse", _hash(f"{model}:{_normalize_query_for_cache(text)}"), sparse_vector
        )
        lf.update_current_span(output={"stored": True})

    # ========== Convenience: Search Results ==========

    @observe(name="cache-search-get", capture_input=False, capture_output=False)
    async def get_search_results(
        self, embedding_prefix: list[float], filters: dict | None = None
    ) -> list[dict] | None:
        """Get cached search results by embedding prefix + filters hash."""
        lf = get_client()
        lf.update_current_span(
            input={
                "embedding_prefix_dim": len(embedding_prefix),
                "filters_count": len(filters or {}),
            }
        )
        key = _hash(str(embedding_prefix[:10]) + json.dumps(filters, sort_keys=True, default=str))
        result = await self.get_exact("search", key)
        lf.update_current_span(
            output={"hit": result is not None, "results_count": len(result or [])}
        )
        return result

    @observe(name="cache-search-store", capture_input=False, capture_output=False)
    async def store_search_results(
        self,
        embedding_prefix: list[float],
        filters: dict | None,
        results: list[dict],
    ) -> None:
        """Store search results."""
        lf = get_client()
        lf.update_current_span(
            input={
                "embedding_prefix_dim": len(embedding_prefix),
                "filters_count": len(filters or {}),
                "results_count": len(results),
            }
        )
        key = _hash(str(embedding_prefix[:10]) + json.dumps(filters, sort_keys=True, default=str))
        await self.store_exact("search", key, results)
        lf.update_current_span(output={"stored": True, "results_count": len(results)})

    # ========== Convenience: Rerank Results ==========

    def _build_rerank_key(self, query: str, documents: list[dict[str, Any]], top_k: int) -> str:
        doc_fingerprints = [
            {
                "text_hash": _hash(str(doc.get("text", ""))),
                "score": round(float(doc.get("score", 0.0)), 6),
            }
            for doc in documents[:50]
        ]
        payload = {
            "query": _normalize_query_for_cache(query),
            "top_k": top_k,
            "docs": doc_fingerprints,
        }
        return _hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))

    @observe(name="cache-rerank-get", capture_input=False, capture_output=False)
    async def get_rerank_results(
        self, query: str, documents: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]] | None:
        """Get cached rerank results for a query+document set."""
        lf = get_client()
        lf.update_current_span(
            input={
                "query_length": len(query),
                "documents_count": len(documents),
                "top_k": top_k,
            }
        )
        key = self._build_rerank_key(query, documents, top_k)
        result = await self.get_exact("rerank", key)
        lf.update_current_span(
            output={"hit": result is not None, "results_count": len(result or [])}
        )
        return result

    @observe(name="cache-rerank-store", capture_input=False, capture_output=False)
    async def store_rerank_results(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int,
        results: list[dict[str, Any]],
    ) -> None:
        """Store rerank results for a query+document set."""
        lf = get_client()
        lf.update_current_span(
            input={
                "query_length": len(query),
                "documents_count": len(documents),
                "top_k": top_k,
                "results_count": len(results),
            }
        )
        key = self._build_rerank_key(query, documents, top_k)
        await self.store_exact("rerank", key, results)
        lf.update_current_span(output={"stored": True, "results_count": len(results)})

    # ========== Conversation History ==========
    # Legacy store/get methods removed in #157: memory owned by LangGraph checkpointer.

    async def clear_conversation(self, user_id: int) -> None:
        """Clear conversation history for a user."""
        if not self.redis:
            return
        key = f"conversation:{user_id}"
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error("Conversation clear error: %s: %s", type(e).__name__, e)

    # ========== Cache Clearing ==========

    async def clear_by_tier(self, tier: str) -> int:
        """Clear all Redis keys for the given exact cache tier via SCAN + DELETE.

        Args:
            tier: Cache tier name (embeddings, sparse, search, rerank).
                Passing "search" also clears the "rerank" tier (logically linked).

        Returns:
            Number of deleted keys. Returns 0 if Redis is unavailable.
        """
        if not self.redis:
            return 0

        tiers_to_clear = [tier]
        if tier == "search":
            tiers_to_clear.append("rerank")

        total_deleted = 0
        try:
            for t in tiers_to_clear:
                pattern = f"{t}:{CACHE_VERSION}:*"
                keys = [key async for key in self.redis.scan_iter(match=pattern)]
                if keys:
                    deleted = await self.redis.delete(*keys)
                    total_deleted += deleted
                    logger.info("Cleared %d keys for tier '%s'", deleted, t)
                else:
                    logger.debug("No keys found for tier '%s' (pattern: %s)", t, pattern)
        except Exception as e:
            logger.error("Cache clear error (tier=%s): %s: %s", tier, type(e).__name__, e)

        return total_deleted

    async def clear_semantic_cache(self) -> int:
        """Clear all entries in the semantic cache.

        Uses redisvl API (aclear/clear) if available, otherwise falls back
        to Redis SCAN + DELETE on the semantic cache key pattern.

        Returns:
            1 if cleared successfully, 0 if semantic cache is unavailable or on error.
        """
        if not self.semantic_cache:
            return 0

        try:
            if hasattr(self.semantic_cache, "aclear"):
                await self.semantic_cache.aclear()
            elif hasattr(self.semantic_cache, "clear"):
                self.semantic_cache.clear()
            elif self.redis:
                pattern = f"sem:{SEMANTIC_CACHE_VERSION}:*"
                keys = [key async for key in self.redis.scan_iter(match=pattern)]
                if keys:
                    await self.redis.delete(*keys)
                    logger.info("Cleared %d semantic cache keys via SCAN", len(keys))
            logger.info("Semantic cache cleared")
            return 1
        except Exception as e:
            logger.error("Semantic cache clear error: %s: %s", type(e).__name__, e)
            return 0

    async def clear_all_caches(self) -> dict[str, int]:
        """Clear all cache tiers (semantic + all exact tiers).

        Returns:
            Dict mapping tier name to number of deleted keys.
            Semantic returns 1 on success, 0 on failure/unavailable.
        """
        results: dict[str, int] = {}
        results["semantic"] = await self.clear_semantic_cache()
        for tier in ("embeddings", "sparse", "search", "rerank"):
            results[tier] = await self.clear_by_tier(tier)
        return results

    # ========== Metrics ==========

    def get_metrics(self) -> dict[str, Any]:
        """Get hit/miss metrics for all tiers."""
        total_hits = sum(m["hits"] for m in self._metrics.values())
        total_misses = sum(m["misses"] for m in self._metrics.values())
        total = total_hits + total_misses

        result: dict[str, Any] = {}
        for tier, stats in self._metrics.items():
            t = stats["hits"] + stats["misses"]
            result[tier] = {
                "hits": stats["hits"],
                "misses": stats["misses"],
                "hit_rate": round((stats["hits"] / t * 100) if t > 0 else 0, 1),
            }

        result["total_requests"] = total
        result["overall_hit_rate"] = round((total_hits / total * 100) if total > 0 else 0, 1)
        return result

    # ========== Utilities ==========

    @staticmethod
    def make_hash(data: str) -> str:
        """Public hash utility for cache keys."""
        return _hash(data)
