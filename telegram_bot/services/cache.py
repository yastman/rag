"""Redis caching service for RAG pipeline.

Uses native RedisVL SemanticCache for LLM response caching with vector similarity search.

NOTE: redisvl imports are lazy-loaded in initialize() to avoid ~7.5s import overhead
from voyageai SDK (pandas, scipy.stats) during test collection.
"""

import hashlib
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Optional

import redis.asyncio as redis


# Lazy imports for redisvl (heavy dependency chain via voyageai SDK)
# These are imported inside initialize() to speed up test collection
if TYPE_CHECKING:
    from redisvl.extensions.cache.embeddings import EmbeddingsCache
    from redisvl.extensions.cache.llm import SemanticCache
    from redisvl.extensions.message_history import SemanticMessageHistory

logger = logging.getLogger(__name__)

# Cache versioning - bump when changing cache structure or models
CACHE_SCHEMA_VERSION = "v2"


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
        distance_threshold: float = 0.20,  # cosine distance threshold (0.20 ≈ 80% similarity, better for RU paraphrases)
    ):
        """Initialize cache service.

        Args:
            redis_url: Redis connection URL
            semantic_cache_ttl: TTL for semantic cache (seconds)
            embeddings_cache_ttl: TTL for embeddings cache (seconds)
            analyzer_cache_ttl: TTL for QueryAnalyzer cache (seconds)
            search_cache_ttl: TTL for Qdrant search cache (seconds)
            distance_threshold: Cosine distance threshold for semantic cache (lower = stricter)
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
            "rerank": {"hits": 0, "misses": 0},
        }

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

    def _get_vectorizer_id(self) -> str:
        """Get vectorizer identifier for cache namespacing.

        Returns:
            'userbase768' for local USER-base model (768-dim)
            'voyage1024' for Voyage API (1024-dim)
        """
        use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
        if use_local:
            return "userbase768"
        return "voyage1024"

    async def initialize(self):
        """Initialize Redis connections and caches.

        NOTE: redisvl imports happen here (lazy loading) to avoid ~7.5s import
        overhead during test collection. The voyageai SDK pulls in pandas/scipy.
        """
        # Lazy import redisvl components (heavy dependency chain)
        from redisvl.extensions.cache.embeddings import EmbeddingsCache
        from redisvl.extensions.cache.llm import SemanticCache
        from redisvl.extensions.message_history import SemanticMessageHistory
        from redisvl.utils.vectorize import VoyageAITextVectorizer

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
            # Supports local USER-base (best for RU) or Voyage API fallback
            use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"

            try:
                if use_local:
                    # Use local USER-base for Russian semantic matching (ruMTEB #1)
                    from telegram_bot.services.vectorizers import UserBaseVectorizer

                    user_base_url = os.getenv("USER_BASE_URL", "http://localhost:8003")
                    logger.info(f"Initializing SemanticCache with USER-base ({user_base_url})...")
                    vectorizer = UserBaseVectorizer(base_url=user_base_url)
                else:
                    # Fallback to Voyage API
                    voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
                    if not voyage_api_key:
                        logger.warning(
                            "VOYAGE_API_KEY not set and USE_LOCAL_EMBEDDINGS=false, "
                            "SemanticCache disabled"
                        )
                        self.semantic_cache = None
                        vectorizer = None
                    else:
                        logger.info(
                            "Initializing SemanticCache with VoyageAI (voyage-multilingual-2)..."
                        )
                        vectorizer = VoyageAITextVectorizer(
                            model="voyage-multilingual-2",  # Better RU support than voyage-3-lite
                            api_config={"api_key": voyage_api_key},
                        )

                if vectorizer is not None:
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
                    vectorizer_name = "USER-base" if use_local else "voyage-multilingual-2"
                    logger.info(
                        f"✓ RedisVL SemanticCache initialized "
                        f"(vectorizer={vectorizer_name}, distance_threshold={self.distance_threshold}, "
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
                if use_local:
                    # Reuse USER-base for conversation history
                    from telegram_bot.services.vectorizers import UserBaseVectorizer

                    user_base_url = os.getenv("USER_BASE_URL", "http://localhost:8003")
                    history_vectorizer = UserBaseVectorizer(base_url=user_base_url)
                    self.message_history = SemanticMessageHistory(
                        name="rag_conversations",
                        redis_url=self.redis_url,
                        vectorizer=history_vectorizer,
                        distance_threshold=0.3,
                    )
                    logger.info("✓ SemanticMessageHistory initialized (USER-base)")
                else:
                    voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
                    if voyage_api_key:
                        history_vectorizer = VoyageAITextVectorizer(
                            model="voyage-multilingual-2",  # Better RU support
                            api_config={"api_key": voyage_api_key},
                        )
                        self.message_history = SemanticMessageHistory(
                            name="rag_conversations",
                            redis_url=self.redis_url,
                            vectorizer=history_vectorizer,
                            distance_threshold=0.3,
                        )
                        logger.info("✓ SemanticMessageHistory initialized (voyage-multilingual-2)")
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
            # Lazy import Tag (redisvl dependency chain is heavy)
            from redisvl.query.filter import Tag

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

    # ========== TIER 1.5: Sparse Embedding Cache ==========

    async def get_cached_sparse_embedding(
        self, text: str, model_name: str = "bm42"
    ) -> Optional[dict[str, Any]]:
        """Get cached sparse embedding.

        Sparse embeddings are stored as JSON in Redis hash.

        Args:
            text: Text to get sparse embedding for
            model_name: Model name for cache key namespacing

        Returns:
            Cached sparse embedding dict (indices, values) if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            start = time.time()
            key = f"sparse:{model_name}:{self._hash_key(text)}"
            cached = await self.redis_client.hgetall(key)
            latency = (time.time() - start) * 1000

            if cached:
                self.metrics["embeddings"]["hits"] += 1
                logger.debug(f"✓ Sparse cache HIT ({latency:.0f}ms)")
                # Decode from Redis hash format
                return {
                    "indices": json.loads(cached.get("indices", "[]")),
                    "values": json.loads(cached.get("values", "[]")),
                }

            self.metrics["embeddings"]["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"Sparse cache get error: {e}")
            self.metrics["embeddings"]["misses"] += 1
            return None

    async def store_sparse_embedding(
        self,
        text: str,
        sparse_vector: dict[str, Any],
        model_name: str = "bm42",
        ttl: int = 86400,  # 24 hours default
    ):
        """Store sparse embedding in Redis hash.

        Args:
            text: Original text
            sparse_vector: Sparse vector dict with indices and values
            model_name: Model name for cache key namespacing
            ttl: Time to live in seconds
        """
        if not self.redis_client:
            return

        try:
            key = f"sparse:{model_name}:{self._hash_key(text)}"
            await self.redis_client.hset(
                key,
                mapping={
                    "indices": json.dumps(sparse_vector.get("indices", [])),
                    "values": json.dumps(sparse_vector.get("values", [])),
                },
            )
            await self.redis_client.expire(key, ttl)
            logger.debug(f"✓ Stored sparse embedding: {text[:50]}...")
        except Exception as e:
            logger.error(f"Sparse cache store error: {e}")

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

    # ========== TIER 2: Rerank Cache ==========

    async def get_cached_rerank(
        self,
        query_hash: str,
        chunk_ids: list[str],
    ) -> Optional[list[dict[str, Any]]]:
        """Get cached Voyage rerank results.

        Args:
            query_hash: Hash of query embedding
            chunk_ids: List of chunk IDs that were reranked

        Returns:
            Cached rerank results or None
        """
        if not self.redis_client:
            return None

        try:
            chunk_hash = self._hash_key(json.dumps(sorted(chunk_ids)))
            key = f"rag:rerank:v1:{query_hash}:{chunk_hash}"

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
        query_hash: str,
        chunk_ids: list[str],
        results: list[dict[str, Any]],
        ttl: int = 7200,
    ):
        """Store Voyage rerank results (TTL 2 hours)."""
        if not self.redis_client:
            return

        try:
            chunk_hash = self._hash_key(json.dumps(sorted(chunk_ids)))
            key = f"rag:rerank:v1:{query_hash}:{chunk_hash}"

            await self.redis_client.setex(key, ttl, json.dumps(results))
            logger.debug(f"✓ Stored rerank ({len(results)} items)")
        except Exception as e:
            logger.error(f"Rerank cache store error: {e}")

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
