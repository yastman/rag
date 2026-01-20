"""Redis caching service for RAG pipeline."""

import hashlib
import json
import logging
import time
from typing import Any, Optional

import redis.asyncio as redis
from redisvl.extensions.cache.embeddings import EmbeddingsCache


logger = logging.getLogger(__name__)


class CacheService:
    """Multi-level caching service for RAG pipeline.

    Tier 1 (Critical):
    - Semantic cache для финальных LLM ответов (векторный поиск)
    - Embeddings cache для эмбеддингов запросов

    Tier 2 (Medium):
    - QueryAnalyzer результаты (exact match)
    - Qdrant search результаты (exact match)
    """

    def __init__(
        self,
        redis_url: str,
        semantic_cache_ttl: int = 48 * 3600,  # 48 hours
        embeddings_cache_ttl: int = 7 * 24 * 3600,  # 7 days
        analyzer_cache_ttl: int = 24 * 3600,  # 24 hours
        search_cache_ttl: int = 2 * 3600,  # 2 hours
        distance_threshold: float = 0.85,  # semantic similarity threshold
    ):
        """Initialize cache service.

        Args:
            redis_url: Redis connection URL
            semantic_cache_ttl: TTL for semantic cache (seconds)
            embeddings_cache_ttl: TTL for embeddings cache (seconds)
            analyzer_cache_ttl: TTL for QueryAnalyzer cache (seconds)
            search_cache_ttl: TTL for Qdrant search cache (seconds)
            distance_threshold: Semantic similarity threshold (0.0-1.0)
        """
        self.redis_url = redis_url

        # TTL configuration
        self.semantic_cache_ttl = semantic_cache_ttl
        self.embeddings_cache_ttl = embeddings_cache_ttl
        self.analyzer_cache_ttl = analyzer_cache_ttl
        self.search_cache_ttl = search_cache_ttl

        # Metrics
        self.metrics = {
            "semantic": {"hits": 0, "misses": 0},
            "embeddings": {"hits": 0, "misses": 0},
            "analyzer": {"hits": 0, "misses": 0},
            "search": {"hits": 0, "misses": 0},
        }

        # Initialize Redis client for key-value operations
        self.redis_client: Optional[redis.Redis] = None

        # Initialize RedisVL Embeddings cache (Tier 1)
        self.embeddings_cache: Optional[EmbeddingsCache] = None

        # Distance threshold for semantic cache
        self.distance_threshold = distance_threshold

        logger.info("CacheService initialized with 4-tier architecture")

    async def initialize(self):
        """Initialize Redis connections and caches."""
        try:
            # Initialize async Redis client for Tier 2
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )

            # Test connection
            await self.redis_client.ping()
            logger.info("✓ Redis connection established")

            # Initialize Semantic Cache using Redis vector search
            # Создаем векторный индекс для KNN поиска похожих ответов
            try:
                await self._create_semantic_index()
                logger.info(
                    f"✓ Semantic LLM cache initialized (vector search, threshold={self.distance_threshold})"
                )
            except Exception as e:
                logger.warning(f"Semantic cache index creation warning: {e}")

            # Initialize Embeddings Cache (Tier 1)
            try:
                self.embeddings_cache = EmbeddingsCache(
                    name="rag:embeddings:v1",
                    redis_url=self.redis_url,
                    ttl=self.embeddings_cache_ttl,
                )
                logger.info("✓ Embeddings cache initialized")
            except Exception as e:
                logger.warning(f"Embeddings cache initialization failed: {e}")
                self.embeddings_cache = None

        except Exception as e:
            logger.error(f"Cache initialization error: {e}")
            self.redis_client = None

    async def close(self):
        """Close Redis connections."""
        if self.redis_client:
            await self.redis_client.aclose()
            logger.info("Redis connections closed")

    def _hash_key(self, data: str) -> str:
        """Generate SHA256 hash for cache key."""
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    async def _create_semantic_index(self):
        """Create Redis vector index for semantic search if not exists."""
        index_name = "idx:rag:semantic_cache"

        try:
            # Check if index exists
            await self.redis_client.execute_command("FT.INFO", index_name)
            logger.debug(f"Semantic cache index '{index_name}' already exists")
        except Exception:
            # Create index with vector field (BGE-M3 = 1024 dimensions, COSINE distance)
            await self.redis_client.execute_command(
                "FT.CREATE",
                index_name,
                "ON",
                "HASH",
                "PREFIX",
                "1",
                "rag:semantic:",
                "SCHEMA",
                "query_vector",
                "VECTOR",
                "FLAT",
                "6",
                "TYPE",
                "FLOAT32",
                "DIM",
                "1024",
                "DISTANCE_METRIC",
                "COSINE",
                "answer",
                "TEXT",
                "timestamp",
                "NUMERIC",
            )
            logger.info(f"Created semantic cache index '{index_name}'")

    # ========== TIER 1: Semantic Cache (LLM Answers) ==========

    async def check_semantic_cache(self, query_embedding: list[float]) -> Optional[str]:
        """Check semantic cache using vector similarity search.

        Args:
            query_embedding: Query embedding vector (1024-dim for BGE-M3)

        Returns:
            Cached answer if similar query found (cosine similarity > threshold), None otherwise
        """
        if not self.redis_client:
            return None

        try:
            import numpy as np

            # Convert embedding to bytes for Redis vector search
            vector_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

            start = time.time()

            # KNN search: find most similar cached answer
            # Using COSINE distance, threshold = distance_threshold (0.85 = high similarity)
            result = await self.redis_client.execute_command(
                "FT.SEARCH",
                "idx:rag:semantic_cache",
                "*=>[KNN 1 @query_vector $vec AS score]",
                "PARAMS",
                "2",
                "vec",
                vector_bytes,
                "DIALECT",
                "2",
                "RETURN",
                "2",
                "answer",
                "score",
            )

            latency = (time.time() - start) * 1000

            # Result format: [count, key1, [field1, value1, field2, value2, ...]]
            if result and len(result) > 1 and int(result[0]) > 0:
                # Parse field-value pairs from result
                fields = result[2]
                field_dict = {}
                for i in range(0, len(fields), 2):
                    field_dict[fields[i]] = fields[i + 1]

                # Get similarity score (cosine distance: 0 = identical, 1 = opposite)
                score = float(field_dict.get("score", 1.0))
                similarity = 1 - score  # Convert distance to similarity

                if similarity >= self.distance_threshold:
                    self.metrics["semantic"]["hits"] += 1
                    answer = field_dict.get("answer", "")
                    logger.info(
                        f"✓ Semantic cache HIT ({latency:.0f}ms, similarity={similarity:.3f})"
                    )
                    return answer
                self.metrics["semantic"]["misses"] += 1
                logger.debug(
                    f"✗ Semantic cache MISS (similarity={similarity:.3f} < {self.distance_threshold})"
                )
                return None
            self.metrics["semantic"]["misses"] += 1
            return None

        except Exception as e:
            logger.error(f"Semantic cache error: {e}")
            self.metrics["semantic"]["misses"] += 1
            return None

    async def store_semantic_cache(self, query: str, query_embedding: list[float], answer: str):
        """Store question-answer pair in semantic cache with vector for similarity search.

        Args:
            query: User query text
            query_embedding: Query embedding vector (1024-dim for BGE-M3)
            answer: LLM answer
        """
        if not self.redis_client:
            return

        try:
            import numpy as np

            # Generate unique key for this cache entry
            key = f"rag:semantic:{self._hash_key(query)}"

            # Convert embedding to bytes for Redis vector field
            vector_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

            # Store as Redis Hash with vector field
            mapping = {
                "query_vector": vector_bytes,
                "answer": answer,
                "timestamp": int(time.time()),
                "query": query,  # Store original query for debugging
            }

            await self.redis_client.hset(key, mapping=mapping)

            # Set TTL (48 hours)
            await self.redis_client.expire(key, self.semantic_cache_ttl)

            logger.debug(f"✓ Stored semantic cache: {query[:50]}...")
        except Exception as e:
            logger.error(f"Semantic cache store error: {e}")

    # ========== TIER 1: Embeddings Cache ==========

    async def get_cached_embedding(self, text: str) -> Optional[list[float]]:
        """Get cached embedding for text.

        Args:
            text: Text to get embedding for

        Returns:
            Cached embedding vector if found, None otherwise
        """
        if not self.embeddings_cache or not self.redis_client:
            return None

        try:
            key = f"rag:emb:v1:{self._hash_key(text)}"
            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            if cached:
                self.metrics["embeddings"]["hits"] += 1
                logger.debug(f"✓ Embedding cache HIT ({latency:.0f}ms)")
                return json.loads(cached)
            self.metrics["embeddings"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"Embedding cache error: {e}")
            self.metrics["embeddings"]["misses"] += 1
            return None

    async def store_embedding(self, text: str, embedding: list[float]):
        """Store embedding in cache.

        Args:
            text: Original text
            embedding: Embedding vector
        """
        if not self.redis_client:
            return

        try:
            key = f"rag:emb:v1:{self._hash_key(text)}"
            await self.redis_client.setex(
                key,
                self.embeddings_cache_ttl,
                json.dumps(embedding),
            )
            logger.debug(f"✓ Stored embedding: {text[:50]}...")
        except Exception as e:
            logger.error(f"Embedding cache store error: {e}")

    # ========== TIER 2: QueryAnalyzer Cache ==========

    async def get_cached_analysis(self, query: str) -> Optional[dict[str, Any]]:
        """Get cached QueryAnalyzer result.

        Args:
            query: User query

        Returns:
            Cached analysis dict if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            key = f"rag:analysis:v1:{self._hash_key(query)}"
            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            if cached:
                self.metrics["analyzer"]["hits"] += 1
                logger.info(f"✓ QueryAnalyzer cache HIT ({latency:.0f}ms)")
                return json.loads(cached)
            self.metrics["analyzer"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"QueryAnalyzer cache error: {e}")
            self.metrics["analyzer"]["misses"] += 1
            return None

    async def store_analysis(self, query: str, analysis: dict[str, Any]):
        """Store QueryAnalyzer result in cache.

        Args:
            query: User query
            analysis: Analysis dict with filters and semantic_query
        """
        if not self.redis_client:
            return

        try:
            key = f"rag:analysis:v1:{self._hash_key(query)}"
            await self.redis_client.setex(
                key,
                self.analyzer_cache_ttl,
                json.dumps(analysis),
            )
            logger.debug(f"✓ Stored analysis: {query[:50]}...")
        except Exception as e:
            logger.error(f"QueryAnalyzer cache store error: {e}")

    # ========== TIER 2: Qdrant Search Cache ==========

    async def get_cached_search(
        self, embedding: list[float], filters: Optional[dict[str, Any]], index_version: str = "v1"
    ) -> Optional[list[dict[str, Any]]]:
        """Get cached Qdrant search results.

        Args:
            embedding: Query embedding vector
            filters: Search filters
            index_version: Version of Qdrant index (for invalidation)

        Returns:
            Cached search results if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            # Build cache key from embedding hash + filters + index version
            embedding_hash = self._hash_key(str(embedding[:10]))  # use first 10 dims
            filters_hash = self._hash_key(json.dumps(filters, sort_keys=True) if filters else "")
            key = f"rag:search:v1:{index_version}:{embedding_hash}:{filters_hash}"

            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            if cached:
                self.metrics["search"]["hits"] += 1
                logger.info(f"✓ Search cache HIT ({latency:.0f}ms)")
                return json.loads(cached)
            self.metrics["search"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"Search cache error: {e}")
            self.metrics["search"]["misses"] += 1
            return None

    async def store_search_results(
        self,
        embedding: list[float],
        filters: Optional[dict[str, Any]],
        results: list[dict[str, Any]],
        index_version: str = "v1",
    ):
        """Store Qdrant search results in cache.

        Args:
            embedding: Query embedding vector
            filters: Search filters
            results: Search results
            index_version: Version of Qdrant index
        """
        if not self.redis_client:
            return

        try:
            embedding_hash = self._hash_key(str(embedding[:10]))
            filters_hash = self._hash_key(json.dumps(filters, sort_keys=True) if filters else "")
            key = f"rag:search:v1:{index_version}:{embedding_hash}:{filters_hash}"

            await self.redis_client.setex(
                key,
                self.search_cache_ttl,
                json.dumps(results),
            )
            logger.debug(f"✓ Stored search results ({len(results)} items)")
        except Exception as e:
            logger.error(f"Search cache store error: {e}")

    # ========== Metrics ==========

    def get_metrics(self) -> dict[str, Any]:
        """Get cache metrics."""
        total_hits = sum(m["hits"] for m in self.metrics.values())
        total_misses = sum(m["misses"] for m in self.metrics.values())
        total_requests = sum(m["hits"] + m["misses"] for m in self.metrics.values())

        hit_rates = {}
        for cache_type, stats in self.metrics.items():
            total = stats["hits"] + stats["misses"]
            hit_rate = (stats["hits"] / total * 100) if total > 0 else 0
            hit_rates[cache_type] = {
                "hits": stats["hits"],
                "misses": stats["misses"],
                "requests": total,
                "hit_rate": round(hit_rate, 1),
            }

        return {
            "by_type": hit_rates,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_requests": total_requests,
            "overall_hit_rate": round(
                (total_hits / total_requests * 100) if total_requests > 0 else 0, 1
            ),
        }

    # ============= Conversation Memory (Task 2.2) =============

    async def store_conversation_message(
        self,
        user_id: int,
        role: str,
        content: str,
        max_messages: int = 10,
        ttl: int = 3600,
    ):
        """
        Store conversation message in Redis for multi-turn dialogues.

        Args:
            user_id: Telegram user ID
            role: Message role ('user' or 'assistant')
            content: Message content
            max_messages: Maximum messages to keep (default: 10)
            ttl: Time to live in seconds (default: 1 hour)
        """
        if not self.redis_client:
            return

        key = f"conversation:{user_id}"
        message = json.dumps({"role": role, "content": content, "timestamp": time.time()})

        # Store as JSON string in Redis LIST
        await self.redis_client.lpush(key, message)
        # Keep only last N messages
        await self.redis_client.ltrim(key, 0, max_messages - 1)
        # Set expiration
        await self.redis_client.expire(key, ttl)

        logger.debug(f"Stored conversation message for user {user_id}: {role}")

    async def get_conversation_history(self, user_id: int, last_n: int = 5) -> list[dict[str, Any]]:
        """
        Get conversation history for user.

        Args:
            user_id: Telegram user ID
            last_n: Number of last messages to retrieve

        Returns:
            List of messages [{"role": "user", "content": "...", "timestamp": 123}]
        """
        if not self.redis_client:
            return []

        key = f"conversation:{user_id}"
        messages_json = await self.redis_client.lrange(key, 0, last_n - 1)

        if not messages_json:
            return []

        messages = [json.loads(msg) for msg in messages_json]
        logger.debug(f"Retrieved {len(messages)} messages for user {user_id}")

        return messages

    async def clear_conversation_history(self, user_id: int):
        """Clear conversation history for user."""
        if not self.redis_client:
            return

        key = f"conversation:{user_id}"
        await self.redis_client.delete(key)
        logger.info(f"Cleared conversation history for user {user_id}")

    # ==========================================================

    def log_metrics(self):
        """Log current cache metrics."""
        metrics = self.get_metrics()
        logger.info(
            f"Cache Metrics: {metrics['overall_hit_rate']}% hit rate, {metrics['total_requests']} requests"
        )
        for cache_type, stats in metrics["by_type"].items():
            logger.info(
                f"  {cache_type}: {stats['hit_rate']}% ({stats['hits']}/{stats['hits'] + stats['misses']})"
            )
