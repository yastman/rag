"""Redis caching service for RAG pipeline.

Uses native RedisVL SemanticCache for LLM response caching with vector similarity search.
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

import redis.asyncio as redis
from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.extensions.message_history import SemanticMessageHistory
from redisvl.query.filter import Tag
from redisvl.utils.vectorize import VoyageAITextVectorizer


logger = logging.getLogger(__name__)


class CacheService:
    """Multi-level caching service for RAG pipeline.

    Tier 1 (Critical):
    - Semantic cache для финальных LLM ответов (RedisVL SemanticCache)
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
        rerank_cache_ttl: int = 2 * 3600,  # 2 hours (same as search)
        sparse_cache_ttl: int = 7 * 24 * 3600,  # 7 days (same as embeddings)
        distance_threshold: float = 0.15,  # cosine distance threshold (0.15 ≈ 85% similarity)
    ):
        """Initialize cache service.

        Args:
            redis_url: Redis connection URL
            semantic_cache_ttl: TTL for semantic cache (seconds)
            embeddings_cache_ttl: TTL for embeddings cache (seconds)
            analyzer_cache_ttl: TTL for QueryAnalyzer cache (seconds)
            search_cache_ttl: TTL for Qdrant search cache (seconds)
            rerank_cache_ttl: TTL for Voyage rerank cache (seconds)
            sparse_cache_ttl: TTL for sparse embeddings cache (seconds)
            distance_threshold: Cosine distance threshold for semantic cache (lower = stricter)
        """
        self.redis_url = redis_url

        # TTL configuration
        self.semantic_cache_ttl = semantic_cache_ttl
        self.embeddings_cache_ttl = embeddings_cache_ttl
        self.analyzer_cache_ttl = analyzer_cache_ttl
        self.search_cache_ttl = search_cache_ttl
        self.rerank_cache_ttl = rerank_cache_ttl
        self.sparse_cache_ttl = sparse_cache_ttl

        # Metrics
        self.metrics = {
            "semantic": {"hits": 0, "misses": 0},
            "embeddings": {"hits": 0, "misses": 0},
            "analyzer": {"hits": 0, "misses": 0},
            "search": {"hits": 0, "misses": 0},
            "rerank": {"hits": 0, "misses": 0},
            "sparse": {"hits": 0, "misses": 0},
        }

        # Latency tracking (2026 best practice)
        # Stores last N latencies per cache type for p50/p95 calculation
        self._latency_samples: dict[str, list[float]] = {
            "semantic": [],
            "embeddings": [],
            "analyzer": [],
            "search": [],
            "rerank": [],
            "sparse": [],
        }
        self._max_latency_samples = 1000  # Keep last 1000 samples per type

        # Initialize Redis client for key-value operations (Tier 2)
        self.redis_client: Optional[redis.Redis] = None

        # Native RedisVL SemanticCache (Tier 1)
        self.semantic_cache: Optional[SemanticCache] = None

        # Native RedisVL EmbeddingsCache (Tier 1)
        self.embeddings_cache: Optional[EmbeddingsCache] = None

        # Cosine distance threshold for semantic cache
        self.distance_threshold = distance_threshold

        # Native RedisVL SemanticMessageHistory (for conversation context)
        self.message_history: Optional[SemanticMessageHistory] = None

        logger.info("CacheService initialized with 4-tier architecture (RedisVL native)")

    async def initialize(self):
        """Initialize Redis connections and caches."""
        try:
            # Initialize async Redis client for Tier 2 (key-value caches)
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

            # Initialize native RedisVL SemanticCache (Tier 1)
            # Uses VoyageAI voyage-3-lite for fast, cost-effective cache matching
            # BGE-M3 (1024-dim) is used separately for Qdrant search
            try:
                voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
                if not voyage_api_key:
                    logger.warning("VOYAGE_API_KEY not set, SemanticCache disabled")
                    self.semantic_cache = None
                else:
                    logger.info("Initializing SemanticCache with VoyageAI (voyage-3-lite)...")
                    vectorizer = VoyageAITextVectorizer(
                        model="voyage-3-lite",
                        api_config={"api_key": voyage_api_key},
                    )
                    self.semantic_cache = SemanticCache(
                        name="rag_llm_cache",
                        redis_url=self.redis_url,
                        ttl=self.semantic_cache_ttl,
                        distance_threshold=self.distance_threshold,
                        vectorizer=vectorizer,
                        filterable_fields=[
                            {"name": "user_id", "type": "tag"},
                            {"name": "language", "type": "tag"},
                            {"name": "query_type", "type": "tag"},
                        ],
                    )
                    logger.info(
                        f"✓ RedisVL SemanticCache initialized "
                        f"(vectorizer=voyage-3-lite, distance_threshold={self.distance_threshold}, "
                        f"filterable_fields=[user_id, language, query_type])"
                    )
            except Exception as e:
                logger.warning(f"SemanticCache initialization failed: {e}")
                self.semantic_cache = None

            # Initialize native EmbeddingsCache (Tier 1)
            try:
                self.embeddings_cache = EmbeddingsCache(
                    name="bge_m3_embeddings",
                    redis_url=self.redis_url,
                    ttl=self.embeddings_cache_ttl,
                )
                logger.info("✓ EmbeddingsCache initialized (native RedisVL)")
            except Exception as e:
                logger.warning(f"EmbeddingsCache initialization failed: {e}")
                self.embeddings_cache = None

            # Initialize SemanticMessageHistory for conversation context
            try:
                voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
                if voyage_api_key:
                    history_vectorizer = VoyageAITextVectorizer(
                        model="voyage-3-lite",
                        api_config={"api_key": voyage_api_key},
                    )
                    self.message_history = SemanticMessageHistory(
                        name="rag_conversations",
                        redis_url=self.redis_url,
                        vectorizer=history_vectorizer,  # Reuse voyage-3-lite
                        distance_threshold=0.3,
                    )
                    logger.info("✓ SemanticMessageHistory initialized (voyage-3-lite)")
                else:
                    logger.warning("VOYAGE_API_KEY not set, SemanticMessageHistory disabled")
                    self.message_history = None
            except Exception as e:
                logger.warning(f"SemanticMessageHistory initialization failed: {e}")
                self.message_history = None

        except Exception as e:
            logger.error(f"Cache initialization error: {e}")
            self.redis_client = None

    async def close(self):
        """Close Redis connections."""
        if self.semantic_cache:
            await self.semantic_cache.adisconnect()
        if self.embeddings_cache:
            await self.embeddings_cache.adisconnect()
        if self.redis_client:
            await self.redis_client.aclose()
        logger.info("Redis connections closed")

    def _hash_key(self, data: str) -> str:
        """Generate SHA256 hash for cache key."""
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    # ========== TIER 1: Semantic Cache (LLM Answers) ==========

    async def check_semantic_cache(
        self,
        query: str,
        user_id: Optional[int] = None,
        language: str = "ru",
        threshold_override: Optional[float] = None,
    ) -> Optional[str]:
        """Check semantic cache using RedisVL with VoyageAI voyage-3-lite.

        Uses VoyageAI voyage-3-lite for fast, cost-effective cache matching.
        This is separate from BGE-M3 (1024-dim) used for Qdrant search.
        Supports multi-user isolation via filterable_fields.

        Args:
            query: User query text
            user_id: Optional user ID for cache isolation (Telegram user ID)
            language: Language code for filtering (default: "ru")
            threshold_override: Optional distance threshold override for adaptive caching

        Returns:
            Cached answer if similar query found, None otherwise
        """
        if not self.semantic_cache:
            return None

        try:
            start = time.time()

            # Use override if provided, otherwise use default
            effective_threshold = (
                threshold_override if threshold_override is not None else self.distance_threshold
            )

            # Build filter expression for multi-user isolation
            filter_expr = Tag("language") == language

            if user_id is not None:
                filter_expr = filter_expr & (Tag("user_id") == str(user_id))

            # Use native RedisVL acheck - vectorizer computes embedding internally
            results = await self.semantic_cache.acheck(
                prompt=query,
                filter_expression=filter_expr,
                num_results=1,
                distance_threshold=effective_threshold,
            )

            latency = (time.time() - start) * 1000

            if results:
                self.metrics["semantic"]["hits"] += 1
                answer = results[0].get("response", "")
                distance = results[0].get("vector_distance", 0)
                logger.info(f"✓ Semantic cache HIT ({latency:.0f}ms, distance={distance:.3f})")
                return answer

            self.metrics["semantic"]["misses"] += 1
            logger.debug("✗ Semantic cache MISS (no similar results)")
            return None

        except Exception as e:
            logger.error(f"Semantic cache error: {e}")
            self.metrics["semantic"]["misses"] += 1
            return None

    async def store_semantic_cache(
        self,
        query: str,
        answer: str,
        user_id: Optional[int] = None,
        language: str = "ru",
        query_type: str = "general",
    ):
        """Store question-answer pair in semantic cache using RedisVL.

        Uses VoyageAI voyage-3-lite for cache indexing.
        Stores with user context filters for multi-user isolation.

        Args:
            query: User query text
            answer: LLM answer
            user_id: User ID for cache isolation (Telegram user ID)
            language: Language code (default: "ru")
            query_type: Query type for categorization (default: "general")
        """
        if not self.semantic_cache:
            return

        try:
            # Build filters for multi-user isolation
            filters = {
                "language": language,
                "query_type": query_type,
            }
            if user_id is not None:
                filters["user_id"] = str(user_id)

            # Use native RedisVL astore - vectorizer computes embedding internally
            await self.semantic_cache.astore(
                prompt=query,
                response=answer,
                filters=filters,
            )
            logger.debug(f"✓ Stored semantic cache: {query[:50]}... (user_id={user_id})")
        except Exception as e:
            logger.error(f"Semantic cache store error: {e}")

    # ========== TIER 1: Embeddings Cache (Native RedisVL) ==========

    async def get_cached_embedding(
        self, text: str, model_name: str = "bge-m3"
    ) -> Optional[list[float]]:
        """Get cached embedding using native EmbeddingsCache.

        Args:
            text: Text to get embedding for
            model_name: Model name for cache key namespacing

        Returns:
            Cached embedding vector if found, None otherwise
        """
        if not self.embeddings_cache:
            return None

        try:
            start = time.time()
            result = await self.embeddings_cache.aget(
                content=text,
                model_name=model_name,
            )
            latency = (time.time() - start) * 1000

            if result:
                self.metrics["embeddings"]["hits"] += 1
                logger.debug(f"✓ Embedding cache HIT ({latency:.0f}ms)")
                return result["embedding"]

            self.metrics["embeddings"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"EmbeddingsCache error: {e}")
            self.metrics["embeddings"]["misses"] += 1
            return None

    async def store_embedding(
        self,
        text: str,
        embedding: list[float],
        model_name: str = "bge-m3",
        metadata: Optional[dict] = None,
    ):
        """Store embedding in native EmbeddingsCache.

        Args:
            text: Original text
            embedding: Embedding vector
            model_name: Model name for cache key namespacing
            metadata: Optional metadata to store with embedding
        """
        if not self.embeddings_cache:
            return

        try:
            await self.embeddings_cache.aset(
                content=text,
                model_name=model_name,
                embedding=embedding,
                metadata=metadata or {},
            )
            logger.debug(f"✓ Stored embedding: {text[:50]}...")
        except Exception as e:
            logger.error(f"EmbeddingsCache store error: {e}")

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

    # ========== TIER 2: Voyage Rerank Cache (2026 best practice) ==========

    async def get_cached_rerank(
        self,
        query_embedding: list[float],
        doc_ids: list[str],
        collection: str = "default",
        model_version: str = "v1",
    ) -> Optional[list[tuple[str, float]]]:
        """Get cached Voyage rerank results.

        Uses semantic key based on query_embedding_hash for paraphrase matching.

        Args:
            query_embedding: Query embedding vector (for semantic key)
            doc_ids: List of document IDs being reranked
            collection: Collection name for namespace isolation
            model_version: Rerank model version for cache invalidation

        Returns:
            List of (doc_id, score) tuples if cached, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            # Semantic key: use embedding hash for paraphrase matching
            q_emb_hash = self._hash_key(str(query_embedding[:16]))[:16]
            doc_ids_hash = self._hash_key(json.dumps(sorted(doc_ids)))[:16]
            key = f"voyage_rerank:{model_version}:{collection}:{q_emb_hash}:{doc_ids_hash}"

            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            if cached:
                self.metrics["rerank"]["hits"] += 1
                logger.info(f"✓ Rerank cache HIT ({latency:.0f}ms)")
                return json.loads(cached)

            self.metrics["rerank"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"Rerank cache error: {e}")
            self.metrics["rerank"]["misses"] += 1
            return None

    async def store_rerank_results(
        self,
        query_embedding: list[float],
        doc_ids: list[str],
        results: list[tuple[str, float]],
        collection: str = "default",
        model_version: str = "v1",
    ):
        """Store Voyage rerank results in cache.

        Args:
            query_embedding: Query embedding vector
            doc_ids: List of document IDs that were reranked
            results: List of (doc_id, score) tuples
            collection: Collection name
            model_version: Rerank model version
        """
        if not self.redis_client:
            return

        try:
            q_emb_hash = self._hash_key(str(query_embedding[:16]))[:16]
            doc_ids_hash = self._hash_key(json.dumps(sorted(doc_ids)))[:16]
            key = f"voyage_rerank:{model_version}:{collection}:{q_emb_hash}:{doc_ids_hash}"

            await self.redis_client.setex(
                key,
                self.rerank_cache_ttl,
                json.dumps(results),
            )
            logger.debug(f"✓ Stored rerank results ({len(results)} items)")
        except Exception as e:
            logger.error(f"Rerank cache store error: {e}")

    # ========== TIER 2: Sparse Embeddings Cache (BM42) ==========

    async def get_cached_sparse_embedding(
        self, text: str, model_name: str = "bm42"
    ) -> Optional[dict[str, Any]]:
        """Get cached sparse embedding (BM42).

        Args:
            text: Text to get sparse embedding for
            model_name: Sparse model name for cache key namespacing

        Returns:
            Cached sparse embedding dict {indices: [...], values: [...]} if found
        """
        if not self.redis_client:
            return None

        try:
            key = f"sparse_emb:{model_name}:{self._hash_key(text)}"
            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            if cached:
                self.metrics["sparse"]["hits"] += 1
                logger.debug(f"✓ Sparse embedding cache HIT ({latency:.0f}ms)")
                return json.loads(cached)

            self.metrics["sparse"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"Sparse embedding cache error: {e}")
            self.metrics["sparse"]["misses"] += 1
            return None

    async def store_sparse_embedding(
        self,
        text: str,
        sparse_embedding: dict[str, Any],
        model_name: str = "bm42",
    ):
        """Store sparse embedding in cache.

        Args:
            text: Original text
            sparse_embedding: Sparse embedding dict {indices: [...], values: [...]}
            model_name: Sparse model name
        """
        if not self.redis_client:
            return

        try:
            key = f"sparse_emb:{model_name}:{self._hash_key(text)}"
            await self.redis_client.setex(
                key,
                self.sparse_cache_ttl,
                json.dumps(sparse_embedding),
            )
            logger.debug(f"✓ Stored sparse embedding: {text[:50]}...")
        except Exception as e:
            logger.error(f"Sparse embedding cache store error: {e}")

    # ========== Metrics ==========

    def record_latency(self, cache_type: str, latency_ms: float):
        """Record latency sample for a cache type.

        Args:
            cache_type: Type of cache (semantic, embeddings, etc.)
            latency_ms: Latency in milliseconds
        """
        if cache_type not in self._latency_samples:
            return

        samples = self._latency_samples[cache_type]
        samples.append(latency_ms)

        # Keep only last N samples
        if len(samples) > self._max_latency_samples:
            self._latency_samples[cache_type] = samples[-self._max_latency_samples :]

    def _calculate_percentile(self, samples: list[float], percentile: int) -> float:
        """Calculate percentile from samples.

        Args:
            samples: List of latency samples
            percentile: Percentile to calculate (e.g., 50, 95)

        Returns:
            Percentile value or 0 if no samples
        """
        if not samples:
            return 0.0

        sorted_samples = sorted(samples)
        index = int(len(sorted_samples) * percentile / 100)
        index = min(index, len(sorted_samples) - 1)
        return round(sorted_samples[index], 1)

    def get_latency_stats(self) -> dict[str, dict[str, float]]:
        """Get latency statistics (p50, p95) for all cache types.

        Returns:
            Dict with p50 and p95 latencies per cache type
        """
        stats = {}
        for cache_type, samples in self._latency_samples.items():
            stats[cache_type] = {
                "p50": self._calculate_percentile(samples, 50),
                "p95": self._calculate_percentile(samples, 95),
                "samples": len(samples),
            }
        return stats

    def get_metrics(self) -> dict[str, Any]:
        """Get cache metrics including hit rates and latencies."""
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
            "latency": self.get_latency_stats(),
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

    # ============= Semantic Message History (Task 4) =============

    async def get_relevant_history(
        self, user_id: int, query: str, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """Get semantically relevant messages from conversation history.

        Uses vector similarity to find messages related to current query.

        Args:
            user_id: Telegram user ID
            query: Current user query for similarity search
            top_k: Number of relevant messages to return

        Returns:
            List of relevant messages [{"role": "user", "content": "..."}]
        """
        if not self.message_history:
            return []

        try:
            messages = await self.message_history.aget_relevant(
                session_tag=str(user_id),
                prompt=query,
                top_k=top_k,
            )
            logger.debug(f"Retrieved {len(messages)} relevant messages for user {user_id}")
            return messages
        except Exception as e:
            logger.error(f"SemanticMessageHistory error: {e}")
            return []

    async def add_semantic_message(self, user_id: int, role: str, content: str):
        """Add message to semantic conversation history.

        Stores message with embedding for later semantic retrieval.

        Args:
            user_id: Telegram user ID
            role: Message role ('user' or 'assistant')
            content: Message content
        """
        if not self.message_history:
            return

        try:
            await self.message_history.aadd_message(
                session_tag=str(user_id),
                role=role,
                content=content,
            )
            logger.debug(f"Added semantic message for user {user_id}: {role}")
        except Exception as e:
            logger.error(f"SemanticMessageHistory add error: {e}")

    # =============================================================

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
