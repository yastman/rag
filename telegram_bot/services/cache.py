"""Redis caching service for RAG pipeline.

Uses native RedisVL SemanticCache for LLM response caching with vector similarity search.

NOTE: redisvl imports are lazy-loaded in initialize() to avoid ~7.5s import overhead
from voyageai SDK (pandas, scipy.stats) during test collection.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any

import redis.asyncio as redis

from telegram_bot.observability import get_client, observe


# Lazy imports for redisvl (heavy dependency chain via voyageai SDK)
# These are imported inside initialize() to speed up test collection
if TYPE_CHECKING:
    from redisvl.extensions.cache.embeddings import EmbeddingsCache
    from redisvl.extensions.cache.llm import SemanticCache
    from redisvl.extensions.message_history import SemanticMessageHistory

logger = logging.getLogger(__name__)


def _langfuse_client():
    """Get Langfuse client, returning None if not configured."""
    with contextlib.suppress(Exception):
        return get_client()
    return None


# Cache versioning - bump when changing cache structure or models
# NOTE: SemanticMessageHistory index is versioned as:
#   rag_conversations:{CACHE_SCHEMA_VERSION}:{vectorizer_id}
#   e.g. rag_conversations:v2:userbase768 or rag_conversations:v2:voyage1024
# Old indices are NOT deleted automatically; clean up manually if needed.
CACHE_SCHEMA_VERSION = "v2"

# TTL strategy: pattern-based TTL for semantic cache entries
# Price/availability queries change frequently → short TTL
PRICE_PATTERNS = re.compile(
    r"цен[аыу]|стоимост|ціна|вартіст|наличи[еи]|наявніст|скидк|знижк|акци[яию]|тариф",
    re.IGNORECASE,
)
# FAQ/stable content queries → long TTL
FAQ_PATTERNS = re.compile(
    r"что\s+такое|как\s+работает|які\s+умови|що\s+таке|как\s+оформить|які\s+документи|порядок|процедура",
    re.IGNORECASE,
)


def get_ttl_for_query(query: str, answer: str = "") -> int:
    """Determine TTL for a semantic cache entry based on query content.

    Price/availability queries get short TTL (30min), FAQ queries get long TTL (24h),
    everything else uses the configurable default.

    Args:
        query: User query text
        answer: LLM answer (reserved for future use)

    Returns:
        TTL in seconds
    """
    if PRICE_PATTERNS.search(query):
        return 1800  # 30 min
    if FAQ_PATTERNS.search(query):
        return 86400  # 24h
    return int(os.getenv("SEMANTIC_CACHE_TTL_DEFAULT", "3600"))


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
        distance_threshold: float | None = None,  # default from SEMANTIC_CACHE_THRESHOLD env
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

        # Resolve distance threshold: explicit arg > env var > 0.10
        if distance_threshold is None:
            distance_threshold = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.10"))

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
        self.redis_client: redis.Redis | None = None

        # Native RedisVL SemanticCache (Tier 1)
        self.semantic_cache: SemanticCache | None = None

        # Native RedisVL EmbeddingsCache (Tier 1)
        self.embeddings_cache: EmbeddingsCache | None = None

        # Cosine distance threshold for semantic cache
        self.distance_threshold = distance_threshold

        # Native RedisVL SemanticMessageHistory (for conversation context)
        self.message_history: SemanticMessageHistory | None = None

        # Last semantic cache hit distance (for pipeline metrics observation)
        self.last_semantic_distance: float | None = None

        logger.info("CacheService initialized with 4-tier architecture (RedisVL native)")

    def _get_vectorizer_id(self) -> str:
        """Get vectorizer identifier for cache namespacing.

        Returns:
            'bge1024' for BGE-M3 vector reuse (1024-dim, default)
            'userbase768' for local USER-base model (768-dim, legacy)
            'voyage1024' for Voyage API (1024-dim, legacy)
        """
        use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
        if use_local:
            return "bge1024"
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
                    # Fast-Lane: reuse BGE-M3 dense vector (1024-dim) for semantic cache.
                    # Vectors are passed via vector= parameter to acheck/astore,
                    # so the vectorizer is only used for Redis index schema creation.
                    from telegram_bot.services.vectorizers import BgeM3CacheVectorizer

                    bge_m3_url = os.getenv("BGE_M3_URL", "http://bge-m3:8000")
                    logger.info(
                        f"Initializing SemanticCache with BGE-M3 vector reuse ({bge_m3_url})..."
                    )
                    vectorizer = BgeM3CacheVectorizer(base_url=bge_m3_url)
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
                    cache_name = f"sem:{CACHE_SCHEMA_VERSION}:{self._get_vectorizer_id()}"
                    self.semantic_cache = SemanticCache(
                        name=cache_name,
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
                    vectorizer_name = (
                        "BGE-M3 (vector reuse)" if use_local else "voyage-multilingual-2"
                    )
                    logger.info(
                        f"✓ RedisVL SemanticCache initialized "
                        f"(vectorizer={vectorizer_name}, distance_threshold={self.distance_threshold}, "
                        f"filterable_fields=[user_id, language, query_type])"
                    )
            except Exception as e:
                logger.warning(f"SemanticCache initialization failed: {type(e).__name__}: {e}")
                self.semantic_cache = None

            # Initialize native EmbeddingsCache (Tier 1)
            try:
                self.embeddings_cache = EmbeddingsCache(
                    name=f"emb:{CACHE_SCHEMA_VERSION}",
                    redis_url=self.redis_url,
                    ttl=self.embeddings_cache_ttl,
                )
                logger.info("✓ EmbeddingsCache initialized (native RedisVL)")
            except Exception as e:
                logger.warning(f"EmbeddingsCache initialization failed: {type(e).__name__}: {e}")
                self.embeddings_cache = None

            # Initialize SemanticMessageHistory for conversation context
            try:
                if use_local:
                    # Reuse USER-base for conversation history
                    from telegram_bot.services.vectorizers import UserBaseVectorizer

                    user_base_url = os.getenv("USER_BASE_URL", "http://localhost:8003")
                    history_vectorizer = UserBaseVectorizer(base_url=user_base_url)
                    history_index_name = (
                        f"rag_conversations:{CACHE_SCHEMA_VERSION}:{self._get_vectorizer_id()}"
                    )
                    self.message_history = SemanticMessageHistory(
                        name=history_index_name,
                        redis_url=self.redis_url,
                        vectorizer=history_vectorizer,
                        distance_threshold=0.3,
                    )
                    logger.info(f"✓ SemanticMessageHistory initialized ({history_index_name})")
                else:
                    voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
                    if voyage_api_key:
                        history_vectorizer = VoyageAITextVectorizer(
                            model="voyage-multilingual-2",  # Better RU support
                            api_config={"api_key": voyage_api_key},
                        )
                        history_index_name = (
                            f"rag_conversations:{CACHE_SCHEMA_VERSION}:{self._get_vectorizer_id()}"
                        )
                        self.message_history = SemanticMessageHistory(
                            name=history_index_name,
                            redis_url=self.redis_url,
                            vectorizer=history_vectorizer,
                            distance_threshold=0.3,
                        )
                        logger.info(f"✓ SemanticMessageHistory initialized ({history_index_name})")
                    else:
                        logger.warning("VOYAGE_API_KEY not set, SemanticMessageHistory disabled")
                        self.message_history = None
            except Exception as e:
                logger.warning(
                    f"SemanticMessageHistory initialization failed: {type(e).__name__}: {e}"
                )
                self.message_history = None

        except Exception as e:
            logger.error(f"Cache initialization error: {type(e).__name__}: {e}")
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

    def set_threshold(self, value: float) -> None:
        """Dynamically update semantic cache distance threshold.

        Updates both the local default and the RedisVL SemanticCache instance.

        Args:
            value: New cosine distance threshold (lower = stricter matching)
        """
        old = self.distance_threshold
        self.distance_threshold = value
        if self.semantic_cache is not None:
            self.semantic_cache.set_threshold(value)
        logger.info("Semantic cache threshold changed: %.3f -> %.3f", old, value)

    async def clear_semantic_index(self) -> int:
        """Clear all entries from the semantic cache index.

        Returns:
            Number of entries cleared (approximate via SCAN count), or 0 if unavailable.
        """
        if self.semantic_cache is None:
            return 0

        # Count entries before clear (approximate)
        count = 0
        if self.redis_client:
            vid = self._get_vectorizer_id()
            prefix = f"sem:{CACHE_SCHEMA_VERSION}:{vid}:"
            async for _key in self.redis_client.scan_iter(match=f"{prefix}*", count=500):
                count += 1

        await self.semantic_cache.aclear()
        logger.info("Semantic cache cleared (%d entries removed)", count)
        return count

    def _hash_key(self, data: str) -> str:
        """Generate SHA256 hash for cache key."""
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    # ========== TIER 1: Semantic Cache (LLM Answers) ==========

    @observe(name="cache-semantic-check")
    async def check_semantic_cache(
        self,
        query: str,
        vector: list[float] | None = None,
        user_id: int | None = None,
        language: str = "ru",
        threshold_override: float | None = None,
        cache_timeout: float = 0.3,
    ) -> str | None:
        """Check semantic cache using pre-computed vector (Fast-Lane).

        When ``vector`` is provided, skips internal vectorizer entirely —
        zero embedding latency. Falls back to prompt-based if no vector.

        Args:
            query: User query text (used as prompt fallback if no vector)
            vector: Pre-computed dense vector (BGE-M3, 1024-dim). Skips vectorizer.
            user_id: Optional user ID for cache isolation (Telegram user ID)
            language: Language code for filtering (default: "ru")
            threshold_override: Optional distance threshold override
            cache_timeout: Max seconds to wait for cache check (default: 0.3s)

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

            # Fast-Lane: pass pre-computed vector, skip internal vectorizer
            check_kwargs: dict = {
                "filter_expression": filter_expr,
                "num_results": 1,
                "distance_threshold": effective_threshold,
            }
            if vector is not None:
                check_kwargs["vector"] = vector
            else:
                check_kwargs["prompt"] = query

            # Timeout guard — cache miss is better than slow cache
            try:
                results = await asyncio.wait_for(
                    self.semantic_cache.acheck(**check_kwargs),
                    timeout=cache_timeout,
                )
            except TimeoutError:
                latency = (time.time() - start) * 1000
                logger.warning(f"Semantic cache timeout ({latency:.0f}ms > {cache_timeout}s)")
                self.metrics["semantic"]["misses"] += 1
                return None

            latency = (time.time() - start) * 1000

            langfuse = _langfuse_client()

            if results:
                self.metrics["semantic"]["hits"] += 1
                answer = results[0].get("response", "")
                distance = results[0].get("vector_distance", 0)
                self.last_semantic_distance = float(distance)
                logger.info(f"✓ Semantic cache HIT ({latency:.0f}ms, distance={distance:.3f})")

                if langfuse:
                    langfuse.update_current_span(
                        output={
                            "hit": True,
                            "layer": "semantic",
                            "distance": distance,
                            "threshold": effective_threshold,
                            "latency_ms": latency,
                        }
                    )

                return answer

            self.metrics["semantic"]["misses"] += 1
            logger.debug(f"✗ Semantic cache MISS ({latency:.0f}ms)")

            if langfuse:
                langfuse.update_current_span(
                    output={
                        "hit": False,
                        "layer": "semantic",
                        "reason": "no_match",
                        "latency_ms": latency,
                    }
                )

            return None

        except Exception as e:
            logger.error(f"Semantic cache error: {type(e).__name__}: {e}")
            self.metrics["semantic"]["misses"] += 1

            langfuse = _langfuse_client()
            if langfuse:
                langfuse.update_current_span(
                    output={"hit": False, "layer": "semantic", "error": repr(e)}
                )

            return None

    @observe(name="cache-semantic-store")
    async def store_semantic_cache(
        self,
        query: str,
        answer: str,
        vector: list[float] | None = None,
        user_id: int | None = None,
        language: str = "ru",
        query_type: str = "general",
        ttl: int | None = None,
    ):
        """Store question-answer pair in semantic cache (Fast-Lane).

        When ``vector`` is provided, skips internal vectorizer — zero latency.

        Args:
            query: User query text
            answer: LLM answer
            vector: Pre-computed dense vector (BGE-M3, 1024-dim). Skips vectorizer.
            user_id: User ID for cache isolation (Telegram user ID)
            language: Language code (default: "ru")
            query_type: Query type for categorization (default: "general")
            ttl: Optional per-entry TTL override (seconds)
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

            # Fast-Lane: pass pre-computed vector, skip internal vectorizer
            store_kwargs: dict = {
                "prompt": query,
                "response": answer,
                "filters": filters,
            }
            if vector is not None:
                store_kwargs["vector"] = vector
            if ttl is not None:
                store_kwargs["ttl"] = ttl

            await self.semantic_cache.astore(**store_kwargs)
            logger.debug(f"✓ Stored semantic cache: {query[:50]}... (user_id={user_id})")
        except Exception as e:
            logger.error(f"Semantic cache store error: {type(e).__name__}: {e}")

    # ========== TIER 1: Embeddings Cache (Native RedisVL) ==========

    async def get_cached_embedding(
        self, text: str, model_name: str = "bge-m3"
    ) -> list[float] | None:
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
            logger.error(f"EmbeddingsCache error: {type(e).__name__}: {e}")
            self.metrics["embeddings"]["misses"] += 1
            return None

    @observe(name="cache-embedding-store")
    async def store_embedding(
        self,
        text: str,
        embedding: list[float],
        model_name: str = "bge-m3",
        metadata: dict | None = None,
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
            logger.error(f"EmbeddingsCache store error: {type(e).__name__}: {e}")

    # ========== TIER 1.5: Sparse Embedding Cache ==========

    async def get_cached_sparse_embedding(
        self, text: str, model_name: str = "bge_m3_sparse"
    ) -> dict[str, Any] | None:
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
            key = f"sparse:{CACHE_SCHEMA_VERSION}:{model_name}:{self._hash_key(text)}"
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
            logger.error(f"Sparse cache get error: {type(e).__name__}: {e}")
            self.metrics["embeddings"]["misses"] += 1
            return None

    @observe(name="cache-sparse-embedding-store")
    async def store_sparse_embedding(
        self,
        text: str,
        sparse_vector: dict[str, Any],
        model_name: str = "bge_m3_sparse",
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
            key = f"sparse:{CACHE_SCHEMA_VERSION}:{model_name}:{self._hash_key(text)}"
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
            logger.error(f"Sparse cache store error: {type(e).__name__}: {e}")

    # ========== TIER 2: QueryAnalyzer Cache ==========

    async def get_cached_analysis(self, query: str) -> dict[str, Any] | None:
        """Get cached QueryAnalyzer result.

        Args:
            query: User query

        Returns:
            Cached analysis dict if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            key = f"analysis:{CACHE_SCHEMA_VERSION}:{self._hash_key(query)}"
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
            logger.error(f"QueryAnalyzer cache error: {type(e).__name__}: {e}")
            self.metrics["analyzer"]["misses"] += 1
            return None

    @observe(name="cache-analysis-store")
    async def store_analysis(self, query: str, analysis: dict[str, Any]):
        """Store QueryAnalyzer result in cache.

        Args:
            query: User query
            analysis: Analysis dict with filters and semantic_query
        """
        if not self.redis_client:
            return

        try:
            key = f"analysis:{CACHE_SCHEMA_VERSION}:{self._hash_key(query)}"
            await self.redis_client.setex(
                key,
                self.analyzer_cache_ttl,
                json.dumps(analysis),
            )
            logger.debug(f"✓ Stored analysis: {query[:50]}...")
        except Exception as e:
            logger.error(f"QueryAnalyzer cache store error: {type(e).__name__}: {e}")

    # ========== TIER 2: Qdrant Search Cache ==========

    @observe(name="cache-search-check")
    async def get_cached_search(
        self, embedding: list[float], filters: dict[str, Any] | None, index_version: str = "v1"
    ) -> list[dict[str, Any]] | None:
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
            key = f"search:{CACHE_SCHEMA_VERSION}:{index_version}:{embedding_hash}:{filters_hash}"

            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            langfuse = get_client()

            if cached:
                self.metrics["search"]["hits"] += 1
                logger.info(f"✓ Search cache HIT ({latency:.0f}ms)")
                langfuse.update_current_span(output={"hit": True, "layer": "retrieval"})
                return json.loads(cached)

            self.metrics["search"]["misses"] += 1
            langfuse.update_current_span(output={"hit": False, "layer": "retrieval"})
            return None
        except Exception as e:
            logger.error(f"Search cache error: {type(e).__name__}: {e}")
            self.metrics["search"]["misses"] += 1
            langfuse = _langfuse_client()
            if langfuse:
                langfuse.update_current_span(
                    output={"hit": False, "layer": "retrieval", "error": repr(e)}
                )
            return None

    @observe(name="cache-search-store")
    async def store_search_results(
        self,
        embedding: list[float],
        filters: dict[str, Any] | None,
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
            key = f"search:{CACHE_SCHEMA_VERSION}:{index_version}:{embedding_hash}:{filters_hash}"

            await self.redis_client.setex(
                key,
                self.search_cache_ttl,
                json.dumps(results),
            )
            logger.debug(f"✓ Stored search results ({len(results)} items)")
        except Exception as e:
            logger.error(f"Search cache store error: {type(e).__name__}: {e}")

    # ========== TIER 2: Rerank Cache ==========

    @observe(name="cache-rerank-check")
    async def get_cached_rerank(
        self,
        query_hash: str,
        chunk_ids: list[str],
    ) -> list[dict[str, Any]] | None:
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
            key = f"rerank:{CACHE_SCHEMA_VERSION}:{query_hash}:{chunk_hash}"

            start = time.time()
            cached = await self.redis_client.get(key)
            latency = (time.time() - start) * 1000

            langfuse = get_client()

            if cached:
                self.metrics["rerank"]["hits"] += 1
                logger.info(f"✓ Rerank cache HIT ({latency:.0f}ms)")
                langfuse.update_current_span(output={"hit": True, "layer": "rerank"})
                return json.loads(cached)

            self.metrics["rerank"]["misses"] += 1
            langfuse.update_current_span(output={"hit": False, "layer": "rerank"})
            return None
        except Exception as e:
            logger.error(f"Rerank cache error: {type(e).__name__}: {e}")
            self.metrics["rerank"]["misses"] += 1
            langfuse = _langfuse_client()
            if langfuse:
                langfuse.update_current_span(
                    output={"hit": False, "layer": "rerank", "error": repr(e)}
                )
            return None

    @observe(name="cache-rerank-store")
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
            key = f"rerank:{CACHE_SCHEMA_VERSION}:{query_hash}:{chunk_hash}"

            await self.redis_client.setex(key, ttl, json.dumps(results))
            logger.debug(f"✓ Stored rerank ({len(results)} items)")
        except Exception as e:
            logger.error(f"Rerank cache store error: {type(e).__name__}: {e}")

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

    async def get_full_metrics(self) -> dict[str, Any]:
        """Get comprehensive cache metrics including Redis stats.

        Returns:
            Dict with cache hit rates and Redis memory/eviction stats
        """
        base_metrics = self.get_metrics()

        if not self.redis_client:
            return base_metrics

        try:
            memory_info = await self.redis_client.info("memory")
            stats_info = await self.redis_client.info("stats")

            base_metrics["redis"] = {
                "used_memory_human": memory_info.get("used_memory_human"),
                "maxmemory_human": memory_info.get("maxmemory_human"),
                "evicted_keys": stats_info.get("evicted_keys", 0),
                "keyspace_hits": stats_info.get("keyspace_hits", 0),
                "keyspace_misses": stats_info.get("keyspace_misses", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to get Redis stats: {type(e).__name__}: {e}")

        return base_metrics

    # ============= Conversation Memory (Task 2.2) =============

    @observe(name="cache-conversation-store")
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
            logger.error(f"SemanticMessageHistory error: {type(e).__name__}: {e}")
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
            logger.error(f"SemanticMessageHistory add error: {type(e).__name__}: {e}")

    # =============================================================

    async def get_redis_diagnostics(self) -> dict[str, Any]:
        """Get extended Redis diagnostics for monitoring.

        Returns:
            Dict with memory usage, hit rate, key counts by prefix,
            eviction count, connected clients, and maxmemory policy.
        """
        if not self.redis_client:
            return {"error": "Redis client not initialized"}

        try:
            # Gather Redis INFO sections in parallel
            memory_info = await self.redis_client.info("memory")
            stats_info = await self.redis_client.info("stats")
            clients_info = await self.redis_client.info("clients")
            server_info = await self.redis_client.info("server")

            # Calculate hit rate
            keyspace_hits = stats_info.get("keyspace_hits", 0)
            keyspace_misses = stats_info.get("keyspace_misses", 0)
            total_keyspace = keyspace_hits + keyspace_misses
            hit_rate = (keyspace_hits / total_keyspace * 100) if total_keyspace > 0 else 0.0

            # Count keys per known prefix using SCAN (non-blocking)
            known_prefixes = [
                f"sparse:{CACHE_SCHEMA_VERSION}:",
                f"analysis:{CACHE_SCHEMA_VERSION}:",
                f"search:{CACHE_SCHEMA_VERSION}:",
                f"rerank:{CACHE_SCHEMA_VERSION}:",
                f"sem:{CACHE_SCHEMA_VERSION}:",
                f"emb:{CACHE_SCHEMA_VERSION}:",
                f"rag_conversations:{CACHE_SCHEMA_VERSION}:",
                "conversation:",
                "user_context:",
            ]

            prefix_counts: dict[str, int] = {}
            for prefix in known_prefixes:
                count = 0
                async for _key in self.redis_client.scan_iter(match=f"{prefix}*", count=500):
                    count += 1
                # Use short display name (strip version suffix)
                display_name = prefix.rstrip(":")
                prefix_counts[display_name] = count

            # Total keys in DB
            db_size = await self.redis_client.dbsize()

            return {
                "used_memory_human": memory_info.get("used_memory_human", "N/A"),
                "maxmemory_human": memory_info.get("maxmemory_human", "0B"),
                "maxmemory_policy": memory_info.get("maxmemory_policy", "N/A"),
                "hit_rate": round(hit_rate, 1),
                "keyspace_hits": keyspace_hits,
                "keyspace_misses": keyspace_misses,
                "evicted_keys": stats_info.get("evicted_keys", 0),
                "connected_clients": clients_info.get("connected_clients", 0),
                "total_keys": db_size,
                "prefix_counts": prefix_counts,
                "redis_version": server_info.get("redis_version", "N/A"),
                "semantic_threshold": self.distance_threshold,
                "semantic_ttl_default": int(os.getenv("SEMANTIC_CACHE_TTL_DEFAULT", "3600")),
            }
        except Exception as e:
            logger.error(f"Redis diagnostics error: {type(e).__name__}: {e}")
            return {"error": str(e)}

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
