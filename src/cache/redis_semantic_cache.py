"""Redis semantic cache with versioning for embeddings and responses."""

import hashlib
import json
import os
from datetime import timedelta

import redis.asyncio as redis
from opentelemetry import trace


class RedisSemanticCache:
    """
    Redis cache with version-aware keys.

    Cache layers:
    1. Embedding cache: index_v{version}_{query_hash} → embedding vector (TTL: 30 days)
    2. Response cache: response_v{version}_{query_hash} → full results (TTL: 5-60 min)

    Key insight: Include config version in cache key!
    - When index is rebuilt → version increments → old cache invalidated
    - Prevents serving stale results from old index
    """

    def __init__(
        self,
        redis_url: str | None = None,
        index_version: str = "1.0.0",
        embedding_ttl_days: int = 30,
        response_ttl_minutes: int = 5,
    ):
        """
        Initialize Redis cache.

        Args:
            redis_url: Redis connection string (defaults to Docker network with env password)
            index_version: Current index version (increment on reindex)
            embedding_ttl_days: TTL for embedding cache
            response_ttl_minutes: TTL for response cache
        """
        # Default: Use Docker network with password from environment
        if redis_url is None:
            redis_password = os.getenv("REDIS_PASSWORD", "")
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = os.getenv("REDIS_PORT", "6379")
            redis_db = os.getenv("REDIS_CACHE_DB", "2")

            if redis_password:
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

        self.redis = redis.from_url(redis_url)
        self.index_version = index_version
        self.embedding_ttl = timedelta(days=embedding_ttl_days)
        self.response_ttl = timedelta(minutes=response_ttl_minutes)

        # Metrics
        self.tracer = trace.get_tracer(__name__)
        self._hits = 0
        self._misses = 0
        self._cost_saved_usd = 0.0

    def _hash_query(self, query: str) -> str:
        """Generate deterministic hash for query."""
        return hashlib.sha256(query.encode()).hexdigest()[:16]

    async def get_embedding(self, query: str) -> list[float] | None:
        """
        Get cached embedding.

        Cache key format: embedding_v{version}_{hash}
        Example: embedding_v1.0.0_a3f2e4d5c1b8
        """
        query_hash = self._hash_query(query)
        cache_key = f"embedding_v{self.index_version}_{query_hash}"

        with self.tracer.start_as_current_span("cache_get_embedding") as span:
            span.set_attribute("cache.key", cache_key)

            cached = await self.redis.get(cache_key)

            if cached:
                self._hits += 1
                span.set_attribute("cache.hit", True)
                span.set_attribute("cache.layer", "embedding")

                # Embedding saved: ~1ms + $0.00001
                self._cost_saved_usd += 0.00001

                return json.loads(cached)

            self._misses += 1
            span.set_attribute("cache.hit", False)
            return None

    async def set_embedding(self, query: str, embedding: list[float]):
        """Cache embedding with TTL."""
        query_hash = self._hash_query(query)
        cache_key = f"embedding_v{self.index_version}_{query_hash}"

        await self.redis.setex(cache_key, self.embedding_ttl, json.dumps(embedding))

    async def get_response(self, query: str, top_k: int) -> dict | None:
        """
        Get cached full response (embedding + search results).

        Cache key format: response_v{version}_{hash}_{top_k}
        Example: response_v1.0.0_a3f2e4d5c1b8_10
        """
        query_hash = self._hash_query(query)
        cache_key = f"response_v{self.index_version}_{query_hash}_{top_k}"

        with self.tracer.start_as_current_span("cache_get_response") as span:
            span.set_attribute("cache.key", cache_key)

            cached = await self.redis.get(cache_key)

            if cached:
                self._hits += 1
                span.set_attribute("cache.hit", True)
                span.set_attribute("cache.layer", "response")

                # Response saved: ~50ms + $0.0001 (embedding + search)
                self._cost_saved_usd += 0.0001

                return json.loads(cached)

            self._misses += 1
            span.set_attribute("cache.hit", False)
            return None

    async def set_response(self, query: str, top_k: int, response: dict):
        """Cache full response with shorter TTL."""
        query_hash = self._hash_query(query)
        cache_key = f"response_v{self.index_version}_{query_hash}_{top_k}"

        await self.redis.setex(cache_key, self.response_ttl, json.dumps(response))

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "cache_hits": self._hits,
            "cache_misses": self._misses,
            "hit_rate": hit_rate,
            "saved_cost_usd": self._cost_saved_usd,
            "index_version": self.index_version,
        }


# Usage in RAG pipeline
class CachedRAGPipeline:
    """RAG Pipeline with Redis semantic cache."""

    def __init__(self):
        self.cache = RedisSemanticCache(index_version="1.0.0")
        # self.embedder = BGEEmbedder()
        # self.search_engine = DBSFColBERTSearchEngine()

    async def query(self, query_text: str, top_k: int = 10):
        """Query with caching."""

        # Try response cache first (full results)
        cached_response = await self.cache.get_response(query_text, top_k)
        if cached_response:
            return cached_response

        # Try embedding cache
        query_embedding = await self.cache.get_embedding(query_text)
        if not query_embedding:
            # Generate embedding
            query_embedding = await self.embedder.embed(query_text)
            await self.cache.set_embedding(query_text, query_embedding)

        # Search
        results = self.search_engine.search(query_embedding, top_k=top_k)

        response = {"query": query_text, "results": results}

        # Cache full response
        await self.cache.set_response(query_text, top_k, response)

        return response
