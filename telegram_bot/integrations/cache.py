"""CacheLayerManager — 6-tier Redis cache for RAG pipeline.

Replaces CacheService (1000+ LOC) with a focused ~300 LOC implementation.

Tiers:
  1. Semantic cache (RedisVL SemanticCache, threshold per query_type)
  2. Embeddings cache (Redis exact, 7d TTL)
  3. Sparse embeddings cache (Redis exact, 7d TTL)
  4. Analysis cache (Redis exact, 24h TTL)
  5. Search results cache (Redis exact, 2h TTL)
  6. Rerank results cache (Redis exact, 2h TTL)
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
import time
from typing import TYPE_CHECKING, Any

import redis.asyncio as redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

from telegram_bot.observability import observe


if TYPE_CHECKING:
    from redisvl.extensions.cache.llm import SemanticCache

logger = logging.getLogger(__name__)

CACHE_VERSION = "v4"

# Default TTLs per exact-cache tier (seconds)
DEFAULT_TTLS: dict[str, int] = {
    "embeddings": 7 * 86400,  # 7 days
    "sparse": 7 * 86400,  # 7 days
    "analysis": 86400,  # 24 hours
    "search": 7200,  # 2 hours
    "rerank": 7200,  # 2 hours
}

_METRIC_TIERS = ("semantic", "embeddings", "sparse", "analysis", "search", "rerank")


def _hash(data: str) -> str:
    """SHA256 hash truncated to 16 chars for cache keys."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


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
            name=f"sem:{CACHE_VERSION}:bge1024",
            redis_url=redis_url,
            ttl=ttl,
            distance_threshold=distance_threshold,
            vectorizer=vectorizer,
            filterable_fields=[
                {"name": "query_type", "type": "tag"},
                {"name": "language", "type": "tag"},
                {"name": "user_id", "type": "tag"},
            ],
        )
        logger.info("SemanticCache initialized (threshold=%.2f, ttl=%ds)", distance_threshold, ttl)
        return cache
    except Exception as e:
        logger.warning("SemanticCache init failed: %s: %s", type(e).__name__, e)
        return None


class CacheLayerManager:
    """6-tier Redis cache manager for RAG pipeline."""

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

    async def close(self) -> None:
        """Close all connections."""
        if self.semantic_cache:
            with contextlib.suppress(Exception):
                await self.semantic_cache.adisconnect()
        if self.redis:
            await self.redis.aclose()
        logger.info("CacheLayerManager closed")

    # ========== Semantic Cache ==========

    @observe(name="cache-semantic-check")
    async def check_semantic(
        self,
        query: str,
        vector: list[float],
        query_type: str,
        language: str = "ru",
        user_id: int | None = None,
        cache_timeout: float = 0.3,
    ) -> str | None:
        """Check semantic cache with query-type-specific threshold.

        Args:
            query: User query text (fallback if no vector)
            vector: Pre-computed dense embedding (BGE-M3 1024-dim)
            query_type: Query type for threshold selection
            language: Language filter
            user_id: User ID for per-user isolation (Tag filter)
            cache_timeout: Max wait time in seconds (default 0.3s)

        Returns:
            Cached response string, or None on miss/timeout
        """
        if not self.semantic_cache:
            return None

        threshold = self.cache_thresholds.get(query_type, 0.08)

        try:
            from redisvl.query.filter import Tag

            filter_expr = Tag("language") == language
            if user_id is not None:
                filter_expr = filter_expr & (Tag("user_id") == str(user_id))
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
                return str(results[0].get("response", ""))

            self._metrics["semantic"]["misses"] += 1
            logger.debug("Semantic MISS (%.0fms, type=%s)", latency_ms, query_type)
            return None

        except Exception as e:
            logger.error("Semantic cache error: %s: %s", type(e).__name__, e)
            self._metrics["semantic"]["misses"] += 1
            return None

    @observe(name="cache-semantic-store")
    async def store_semantic(
        self,
        query: str,
        response: str,
        vector: list[float],
        query_type: str,
        language: str = "ru",
        user_id: int | None = None,
    ) -> None:
        """Store query-response pair in semantic cache."""
        if not self.semantic_cache:
            return

        ttl = self.cache_ttl.get(query_type, 3600)
        filters: dict[str, str] = {"query_type": query_type, "language": language}
        if user_id is not None:
            filters["user_id"] = str(user_id)
        try:
            await self.semantic_cache.astore(
                prompt=query,
                response=response,
                vector=vector,
                filters=filters,
                ttl=ttl,
            )
            logger.debug("Stored semantic: %s... (type=%s, ttl=%ds)", query[:50], query_type, ttl)
        except Exception as e:
            logger.error("Semantic store error: %s: %s", type(e).__name__, e)

    # ========== Exact Caches (SET/GET) ==========

    @observe(name="cache-exact-get")
    async def get_exact(self, tier: str, key: str) -> Any | None:
        """Get value from exact cache tier.

        Args:
            tier: Cache tier name (embeddings, sparse, analysis, search, rerank)
            key: Cache key (pre-hashed or raw)

        Returns:
            Deserialized value, or None on miss
        """
        if not self.redis:
            return None

        redis_key = f"{tier}:{CACHE_VERSION}:{key}"
        try:
            cached = await self.redis.get(redis_key)
            if cached:
                self._metrics[tier]["hits"] += 1
                return json.loads(cached)
            self._metrics[tier]["misses"] += 1
            return None
        except Exception as e:
            logger.error("Cache get error (%s): %s: %s", tier, type(e).__name__, e)
            self._metrics[tier]["misses"] += 1
            return None

    @observe(name="cache-exact-store")
    async def store_exact(self, tier: str, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value in exact cache tier.

        Args:
            tier: Cache tier name
            key: Cache key
            value: JSON-serializable value
            ttl: Optional TTL override (seconds)
        """
        if not self.redis:
            return

        redis_key = f"{tier}:{CACHE_VERSION}:{key}"
        effective_ttl = ttl or self.exact_ttls.get(tier, 3600)
        try:
            await self.redis.setex(redis_key, effective_ttl, json.dumps(value))
        except Exception as e:
            logger.error("Cache store error (%s): %s: %s", tier, type(e).__name__, e)

    # ========== Convenience: Embeddings ==========

    @observe(name="cache-embedding-get")
    async def get_embedding(self, text: str, model: str = "bge-m3") -> list[float] | None:
        """Get cached dense embedding."""
        return await self.get_exact("embeddings", _hash(f"{model}:{text}"))

    @observe(name="cache-embedding-store")
    async def store_embedding(
        self, text: str, embedding: list[float], model: str = "bge-m3"
    ) -> None:
        """Store dense embedding."""
        await self.store_exact("embeddings", _hash(f"{model}:{text}"), embedding)

    # ========== Convenience: Sparse Embeddings ==========

    async def get_sparse_embedding(
        self, text: str, model: str = "bge_m3_sparse"
    ) -> dict[str, Any] | None:
        """Get cached sparse embedding."""
        return await self.get_exact("sparse", _hash(f"{model}:{text}"))

    async def store_sparse_embedding(
        self, text: str, sparse_vector: dict[str, Any], model: str = "bge_m3_sparse"
    ) -> None:
        """Store sparse embedding."""
        await self.store_exact("sparse", _hash(f"{model}:{text}"), sparse_vector)

    # ========== Convenience: Search Results ==========

    async def get_search_results(
        self, embedding_prefix: list[float], filters: dict | None = None
    ) -> list[dict] | None:
        """Get cached search results by embedding prefix + filters hash."""
        key = _hash(str(embedding_prefix[:10]) + json.dumps(filters, sort_keys=True, default=str))
        return await self.get_exact("search", key)

    async def store_search_results(
        self,
        embedding_prefix: list[float],
        filters: dict | None,
        results: list[dict],
    ) -> None:
        """Store search results."""
        key = _hash(str(embedding_prefix[:10]) + json.dumps(filters, sort_keys=True, default=str))
        await self.store_exact("search", key, results)

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
