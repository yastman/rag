"""Main Telegram bot logic."""

import asyncio
import hashlib
import logging
import os
import time
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from .config import BotConfig
from .middlewares import setup_error_middleware, setup_throttling_middleware
from .observability import get_client, observe
from .services import (
    CacheService,
    CESCPersonalizer,
    HyDEGenerator,
    LLMService,
    PipelineMetrics,
    QdrantService,
    QueryAnalyzer,
    QueryPreprocessor,
    QueryType,
    SmallToBigService,
    UserContextService,
    VoyageService,
    classify_query,
    get_chitchat_response,
    get_off_topic_response,
    is_off_topic,
    is_personalized_query,
    needs_rerank,
)
from .services.cache import CACHE_SCHEMA_VERSION, get_ttl_for_query
from .services.normalizer import normalize_ru_uk
from .services.redis_monitor import RedisHealthMonitor


logger = logging.getLogger(__name__)


def _langfuse_client():
    """Get Langfuse client, returning None if not configured."""
    try:
        return get_client()
    except Exception:
        return None


def make_session_id(session_type: str, identifier: int | str) -> str:
    """Create unified session_id format: {type}-{hash}-{YYYYMMDD}.

    Args:
        session_type: Type prefix (e.g., 'chat', 'smoke', 'load')
        identifier: Unique identifier (chat_id, user_id, etc.)

    Returns:
        Formatted session_id: "chat-a1b2c3d4-20260202"
    """
    id_hash = hashlib.sha256(str(identifier).encode()).hexdigest()[:8]
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    return f"{session_type}-{id_hash}-{date_str}"


class PropertyBot:
    """Telegram bot for Bulgarian property search."""

    def __init__(self, config: BotConfig):
        """Initialize bot with services."""
        self.config = config
        self.bot = Bot(token=config.telegram_token)
        self.dp = Dispatcher()

        # Initialize services
        self.cache_service = CacheService(redis_url=config.redis_url)
        self.query_analyzer = QueryAnalyzer(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
        )
        # Dense embedding provider (feature flag)
        # RETRIEVAL_DENSE_PROVIDER: bge_m3_api | voyage
        if config.retrieval_dense_provider == "bge_m3_api":
            from .services.bge_m3_dense import BgeM3DenseService

            self.dense_service = BgeM3DenseService(base_url=config.bge_m3_url)
            self.voyage_service = None  # Not needed for dense
            logger.info("Using BgeM3DenseService for dense embeddings")
        else:
            # Voyage (default)
            self.voyage_service = VoyageService(
                api_key=config.voyage_api_key,
                model_docs=config.voyage_model_docs,
                model_queries=config.voyage_model_queries,
                model_rerank=config.voyage_model_rerank,
            )
            self.dense_service = self.voyage_service
            logger.info("Using VoyageService for dense embeddings")

        # Rerank provider (feature flag)
        # RERANK_PROVIDER: colbert | none | voyage
        if config.rerank_provider == "colbert":
            from .services.colbert_reranker import ColbertRerankerService

            self.rerank_service = ColbertRerankerService(base_url=config.bge_m3_url)
            logger.info("Using ColbertRerankerService for reranking")
        elif config.rerank_provider == "none":
            self.rerank_service = None
            logger.info("Reranking disabled")
        else:
            # Voyage (default) - need VoyageService for rerank
            if self.voyage_service is None:
                self.voyage_service = VoyageService(
                    api_key=config.voyage_api_key,
                    model_docs=config.voyage_model_docs,
                    model_queries=config.voyage_model_queries,
                    model_rerank=config.voyage_model_rerank,
                )
            self.rerank_service = self.voyage_service
            logger.info("Using VoyageService for reranking")
        # Qdrant service with hybrid search, score boosting, MMR
        self.qdrant_service = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
            quantization_mode=config.qdrant_quantization_mode,
        )
        self.small_to_big_service = SmallToBigService(
            client=self.qdrant_service.client,
            collection_name=self.qdrant_service.collection_name,
            max_expanded_chunks=config.max_expanded_chunks,
            max_context_tokens=config.max_context_tokens,
        )

        # BGE-M3 sparse embedding service (HTTP client, lazy init)
        self._http_client: httpx.AsyncClient | None = None
        self.llm_service = LLMService(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
            low_confidence_threshold=config.low_confidence_threshold,
        )

        # Query preprocessor (rule-based: translit, RRF weights, HyDE gating)
        self.query_preprocessor = QueryPreprocessor()

        # HyDE generator (optional, feature-flagged)
        self.hyde_generator: HyDEGenerator | None = None
        if config.use_hyde:
            self.hyde_generator = HyDEGenerator(
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
                model=config.llm_model,
            )
            logger.info("HyDE enabled (min_words=%d)", config.hyde_min_words)

        # CESC: User context and personalization (configurable)
        self.user_context_service = UserContextService(
            cache_service=self.cache_service,
            llm_service=self.llm_service,
            context_ttl=config.user_context_ttl,
            extraction_frequency=config.cesc_extraction_frequency,
        )
        self.cesc_personalizer = CESCPersonalizer(
            llm_service=self.llm_service,
        )

        # Redis health monitor (periodic background task)
        self._redis_monitor = RedisHealthMonitor(redis_url=config.redis_url)

        # Track initialization state
        self._cache_initialized = False

        # Setup middlewares (before handlers)
        self._setup_middlewares()

        # Register handlers
        self._register_handlers()

    def _setup_middlewares(self):
        """Setup bot middlewares."""
        # Rate limiting: 1.5 seconds between requests
        setup_throttling_middleware(self.dp, rate_limit=1.5, admin_ids=self.config.admin_ids)

        # Error handling middleware
        setup_error_middleware(self.dp)

        logger.info("Middlewares configured")

    def _register_handlers(self):
        """Register message handlers."""
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("help"))(self.cmd_help)
        self.dp.message(Command("clear"))(self.cmd_clear)
        self.dp.message(Command("stats"))(self.cmd_stats)
        self.dp.message(Command("cache_stats"))(self.cmd_cache_stats)
        self.dp.message(Command("cache_threshold"))(self.cmd_cache_threshold)
        self.dp.message(Command("cache_clear"))(self.cmd_cache_clear)
        self.dp.message(Command("metrics"))(self.cmd_metrics)
        self.dp.message(F.text)(self.handle_query)

    async def cmd_start(self, message: Message):
        """Handle /start command."""
        await message.answer(
            "👋 Привет! Я бот по недвижимости в Болгарии.\n\n"
            "Задавай вопросы вроде:\n"
            "• Покажи квартиры дешевле 100 000 евро\n"
            "• 3-комнатные в Солнечный берег\n"
            "• Студии до 350м от моря\n\n"
            "Используй /help для помощи."
        )

    async def cmd_help(self, message: Message):
        """Handle /help command."""
        await message.answer(
            "🔍 Примеры запросов:\n\n"
            "По цене:\n"
            "• Дешевле 80 000 евро\n"
            "• От 100к до 150к\n\n"
            "По комнатам:\n"
            "• 2-комнатные квартиры\n"
            "• Трехкомнатная\n"
            "• Студия\n\n"
            "По городу:\n"
            "• В Несебр\n"
            "• Солнечный берег\n\n"
            "Комбинированные:\n"
            "• 3 комнаты в Солнечный берег до 120к\n"
            "• Студия дешевле 60000\n\n"
            "Команды:\n"
            "/clear - Очистить историю диалога\n"
            "/stats - Показать статистику кеша\n"
            "/cache_stats - Диагностика Redis\n"
        )

    async def cmd_clear(self, message: Message):
        """Handle /clear command - clear conversation history."""
        user_id = message.from_user.id
        await self.cache_service.clear_conversation_history(user_id)
        await message.answer("✅ История диалога очищена.")

    async def cmd_stats(self, message: Message):
        """Handle /stats command - show cache statistics."""
        metrics = self.cache_service.get_metrics()

        stats_text = f"""📊 Статистика кеша:

Общая эффективность: {metrics["overall_hit_rate"]}%
Всего запросов: {metrics["total_requests"]}

По типам:
"""
        for cache_type, stats in metrics["by_type"].items():
            stats_text += (
                f"• {cache_type}: {stats['hit_rate']}% ({stats['hits']}/{stats['requests']})\n"
            )

        await message.answer(stats_text)

    async def cmd_cache_stats(self, message: Message):
        """Handle /cache_stats command - show extended Redis diagnostics."""
        diag = await self.cache_service.get_redis_diagnostics()

        if "error" in diag:
            await message.answer(f"Redis diagnostics error: {diag['error']}")
            return

        # Format prefix counts
        prefix_lines = ""
        for prefix, count in diag.get("prefix_counts", {}).items():
            prefix_lines += f"  {prefix:<30s} {count}\n"

        threshold = diag.get("semantic_threshold", "N/A")
        default_ttl = diag.get("semantic_ttl_default", "N/A")

        text = (
            f"```\n"
            f"=== Redis Diagnostics ===\n"
            f"\n"
            f"Memory:       {diag['used_memory_human']}"
            f" / {diag['maxmemory_human']}\n"
            f"Policy:       {diag['maxmemory_policy']}\n"
            f"Evicted keys: {diag['evicted_keys']}\n"
            f"Clients:      {diag['connected_clients']}\n"
            f"Redis ver:    {diag['redis_version']}\n"
            f"\n"
            f"Hit rate:     {diag['hit_rate']}%"
            f"  ({diag['keyspace_hits']}"
            f" hits / {diag['keyspace_misses']} misses)\n"
            f"\n"
            f"=== Semantic Cache ===\n"
            f"\n"
            f"Threshold:    {threshold}\n"
            f"Default TTL:  {default_ttl}s\n"
            f"\n"
            f"=== Keys by prefix ({diag['total_keys']} total) ===\n"
            f"\n"
            f"{prefix_lines}"
            f"```"
        )

        await message.answer(text, parse_mode="Markdown")

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_ids

    async def cmd_cache_threshold(self, message: Message):
        """Handle /cache_threshold command - dynamically set semantic cache threshold (admin only)."""
        user_id = message.from_user.id
        if not self._is_admin(user_id):
            await message.answer("Access denied. Admin only.")
            return

        parts = (message.text or "").split()
        if len(parts) < 2:
            current = self.cache_service.distance_threshold
            await message.answer(f"Current threshold: {current:.3f}\nUsage: /cache_threshold 0.12")
            return

        try:
            value = float(parts[1])
            if not 0.0 < value < 1.0:
                await message.answer("Threshold must be between 0.0 and 1.0 (exclusive).")
                return
        except ValueError:
            await message.answer("Invalid number. Usage: /cache_threshold 0.12")
            return

        old = self.cache_service.distance_threshold
        self.cache_service.set_threshold(value)
        await message.answer(f"Semantic cache threshold updated: {old:.3f} -> {value:.3f}")

    async def cmd_cache_clear(self, message: Message):
        """Handle /cache_clear command - clear semantic cache index (admin only)."""
        user_id = message.from_user.id
        if not self._is_admin(user_id):
            await message.answer("Access denied. Admin only.")
            return

        count = await self.cache_service.clear_semantic_index()
        await message.answer(f"Semantic cache cleared ({count} entries removed).")

    async def cmd_metrics(self, message: Message):
        """Handle /metrics command - show pipeline p50/p95 timing stats."""
        metrics = PipelineMetrics.get()
        text = f"```\n{metrics.format_text()}\n```"
        await message.answer(text, parse_mode="Markdown")

    @observe(name="telegram-message")
    async def handle_query(self, message: Message):
        """Handle user query with multi-level caching RAG pipeline."""
        # Early typing ACK — user sees "typing..." immediately
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

        start_time = time.perf_counter()
        metrics = PipelineMetrics.get()
        query = message.text or ""
        user_id = message.from_user.id
        logger.info(f"Query from {user_id}: {query}")

        # Scores accumulator - defaults are "miss" / "not applied"
        scores = {
            "semantic_cache_hit": 0.0,
            "embeddings_cache_hit": 0.0,
            "search_cache_hit": 0.0,
            "rerank_applied": 0.0,
            "rerank_cache_hit": 0.0,
            "llm_used": 0.0,
            "no_results": 0.0,
            "results_count": 0.0,
            "hyde_used": 0.0,
            "confidence_score": 0.0,
        }
        query_type = QueryType.SIMPLE  # Default for early exceptions

        try:
            # Context fingerprint for cache isolation + trace filtering
            request_id = f"tg:{message.chat.id}:{message.message_id}"
            context_fingerprint = {
                "tenant": "default",
                "lang": "ru",
                "prompt_version": "v2.1",
                "retrieval_version": f"{self.config.voyage_model_queries}-bge_m3-rrf",
                "rerank_version": self.config.voyage_model_rerank,
                "model_id": self.config.llm_model,
                "cache_schema": CACHE_SCHEMA_VERSION,
                "request_id": request_id,
            }

            # Update trace with user context
            langfuse = _langfuse_client()
            if langfuse:
                langfuse.update_current_trace(
                    name="telegram-rag-query",
                    user_id=str(user_id),
                    session_id=make_session_id("chat", message.chat.id),
                    input={"query": query[:200]},
                    metadata=context_fingerprint,
                    tags=["telegram", "rag", context_fingerprint["retrieval_version"]],
                )

            # Query routing (2026 best practice) - skip RAG for chit-chat
            query_type = classify_query(query)
            if query_type == QueryType.CHITCHAT:
                chitchat_response = get_chitchat_response(query)
                if chitchat_response:
                    logger.info("Query routed to CHITCHAT (skipping RAG)")
                    await message.answer(chitchat_response)
                    return

            # Off-topic detection (Guardrails)
            if self.config.enable_off_topic_detection and is_off_topic(query):
                logger.info("Query routed to OFF_TOPIC (skipping RAG)")
                await message.answer(get_off_topic_response())
                return

            # CESC: Lazy routing (2026 best practice) - only update context for personalized queries
            user_context = None
            needs_personalization = False
            if self.config.cesc_enabled:
                user_context = await self.user_context_service.get_context(user_id)
                needs_personalization = is_personalized_query(query, user_context)
                if needs_personalization:
                    await self.user_context_service.update_from_query(user_id, query)
                    logger.debug("CESC: Query needs personalization")
                else:
                    logger.debug("CESC: Skipping (generic query)")

            # Initialize cache on first query if not done yet
            if not self._cache_initialized:
                await self.cache_service.initialize()
                self._cache_initialized = True

            # 0. Query preprocessing (translit + HyDE gating)
            preprocess_result = self.query_preprocessor.analyze(
                query,
                use_hyde=self.config.use_hyde,
                hyde_min_words=self.config.hyde_min_words,
            )

            # 0.1 RU/UK normalizer: strip greetings/politeness for better cache hits
            clean_query = normalize_ru_uk(query)
            if clean_query != query:
                logger.info(
                    "Query normalized",
                    extra={"original": query[:100], "normalized": clean_query[:100]},
                )

            embed_text = clean_query  # Use normalized query for embedding

            # HyDE: generate hypothetical document for short/vague queries
            if preprocess_result["use_hyde"] and self.hyde_generator is not None:
                hypothetical_doc = await self.hyde_generator.generate_hypothetical_document(query)
                if hypothetical_doc and hypothetical_doc != query:
                    embed_text = hypothetical_doc
                    scores["hyde_used"] = 1.0
                    logger.info("HyDE: embedding hypothetical doc instead of query")

            # === FAST-LANE: Dense embed → cache check (vector reuse) ===
            t_embed = time.perf_counter()
            query_vector = await self.cache_service.get_cached_embedding(embed_text)
            if query_vector is None:
                query_vector = await self.dense_service.embed_query(embed_text)
                await self.cache_service.store_embedding(embed_text, query_vector)
                logger.info(f"Generated embedding: {len(query_vector)}-dim")
            else:
                scores["embeddings_cache_hit"] = 1.0
                logger.info(f"✓ Using cached embedding: {len(query_vector)}-dim")
            embed_ms = (time.perf_counter() - t_embed) * 1000
            metrics.record("embed_dense", embed_ms)
            logger.info("embed_dense: %.0fms", embed_ms)

            # Fast-Lane: check semantic cache with pre-computed vector (no vectorizer call)
            t_cache = time.perf_counter()
            cached_answer = await self.cache_service.check_semantic_cache(
                clean_query, vector=query_vector, user_id=user_id
            )
            cache_ms = (time.perf_counter() - t_cache) * 1000
            metrics.record("cache_acheck", cache_ms)
            logger.info("cache_acheck: %.0fms", cache_ms)

            if cached_answer:
                scores["semantic_cache_hit"] = 1.0
                metrics.inc("cache_hit")
                # Observe vector distance from last cache hit
                if self.cache_service.last_semantic_distance is not None:
                    metrics.observe("cache_distance", self.cache_service.last_semantic_distance)
                # CESC: Personalize only if lazy routing determined it's needed
                if needs_personalization and self.cesc_personalizer.should_personalize(
                    user_context
                ):
                    cached_answer = await self.cesc_personalizer.personalize(
                        cached_response=cached_answer,
                        user_context=user_context,
                        query=query,
                    )
                await message.answer(cached_answer, parse_mode="Markdown")
                return  # finally block writes scores

            # === MISS-LANE: parallel sparse + QueryAnalyzer, then search ===
            # Keep typing indicator alive during heavy pipeline work
            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
                await self._run_miss_lane(
                    message,
                    query,
                    clean_query,
                    query_vector,
                    query_type,
                    scores,
                    metrics,
                    needs_personalization,
                    user_context,
                )

        finally:
            # Record total pipeline time
            total_ms = (time.perf_counter() - start_time) * 1000
            metrics.record("total", total_ms)

            # Log summary every 50 queries
            qcount = metrics.inc_queries()
            if qcount % 50 == 0:
                metrics.log_summary()

            # Write all scores - guaranteed on ALL exit paths
            langfuse = _langfuse_client()
            if langfuse:
                query_type_map = {"chitchat": 0, "simple": 1, "complex": 2}
                langfuse.score_current_trace(
                    name="query_type",
                    value=float(query_type_map.get(query_type.value, 1)),
                )
                langfuse.score_current_trace(
                    name="latency_total_ms",
                    value=total_ms,
                )
                for name, value in scores.items():
                    langfuse.score_current_trace(name=name, value=value)

            self.cache_service.log_metrics()

    async def _run_miss_lane(
        self,
        message: Message,
        query: str,
        clean_query: str,
        query_vector: list,
        query_type,
        scores: dict,
        metrics,
        needs_personalization: bool,
        user_context,
    ):
        """Execute the cache-miss pipeline: search -> rerank -> LLM -> cache store."""
        user_id = message.from_user.id
        metrics.inc("cache_miss")
        t_miss = time.perf_counter()

        # Parallel: QueryAnalyzer + Sparse embedding (independent, both cached)
        async def _get_analysis():
            cached = await self.cache_service.get_cached_analysis(clean_query)
            if cached is not None:
                return cached
            result = await self.query_analyzer.analyze(clean_query)
            await self.cache_service.store_analysis(clean_query, result)
            return result

        async def _get_sparse():
            cached = await self.cache_service.get_cached_sparse_embedding(clean_query)
            if cached is not None:
                return cached
            vec = await self._get_sparse_vector(clean_query)
            if vec.get("indices"):
                await self.cache_service.store_sparse_embedding(clean_query, vec)
            return vec

        analysis, sparse_vector = await asyncio.gather(_get_analysis(), _get_sparse())
        miss_parallel_ms = (time.perf_counter() - t_miss) * 1000
        metrics.record("miss_parallel", miss_parallel_ms)
        logger.info("miss_parallel (analyzer+sparse): %.0fms", miss_parallel_ms)

        filters = analysis.get("filters", {})
        semantic_query = analysis.get("semantic_query", query)
        logger.info(f"QueryAnalyzer: filters={filters}, semantic_query={semantic_query}")

        # 4. Search in Qdrant with hybrid search
        t_search = time.perf_counter()
        results = await self.cache_service.get_cached_search(query_vector, filters)
        if results is None:
            # Hybrid RRF search (dense + sparse)
            results = await self.qdrant_service.hybrid_search_rrf(
                dense_vector=query_vector,
                sparse_vector=sparse_vector,
                filters=filters or None,
                top_k=self.config.search_top_k,
                dense_weight=self.config.hybrid_dense_weight,
                sparse_weight=self.config.hybrid_sparse_weight,
                quantization_ignore=not self.config.qdrant_use_quantization,
                quantization_rescore=self.config.qdrant_quantization_rescore,
                quantization_oversampling=self.config.qdrant_quantization_oversampling,
            )

            # MMR diversity reranking (if enabled and enough results)
            if self.config.mmr_enabled and len(results) > self.config.rerank_top_k:
                result_embeddings = [
                    await self.dense_service.embed_query(r["text"]) for r in results[:20]
                ]
                results = self.qdrant_service.mmr_rerank(
                    points=results[:20],
                    embeddings=result_embeddings,
                    lambda_mult=self.config.mmr_lambda,
                    top_k=self.config.rerank_top_k * 2,
                )

            # Rerank with cache
            if (
                results
                and self.rerank_service is not None
                and needs_rerank(query_type, len(results))
            ):
                scores["rerank_applied"] = 1.0
                results = results[: self.config.rerank_candidates_max]
                doc_ids = [r.get("id", str(i)) for i, r in enumerate(results)]

                rerank_query_hash = hashlib.sha256(str(query_vector[:10]).encode()).hexdigest()[:16]
                cached_rerank = await self.cache_service.get_cached_rerank(
                    query_hash=rerank_query_hash,
                    chunk_ids=doc_ids,
                )

                if cached_rerank:
                    scores["rerank_cache_hit"] = 1.0
                    id_to_result = {r.get("id", str(i)): r for i, r in enumerate(results)}
                    results = [
                        id_to_result[item["id"]]
                        for item in cached_rerank
                        if item["id"] in id_to_result
                    ][: self.config.rerank_top_k]
                    logger.info(f"Using cached rerank ({len(results)} results)")
                else:
                    try:
                        doc_texts = [r["text"] for r in results]
                        rerank_results = await self.rerank_service.rerank(
                            query=query,
                            documents=doc_texts,
                            top_k=self.config.rerank_top_k,
                        )
                        rerank_cache_data = [
                            {"id": doc_ids[r["index"]], "score": r.get("score", 0.0)}
                            for r in rerank_results
                        ]
                        await self.cache_service.store_rerank_results(
                            query_hash=rerank_query_hash,
                            chunk_ids=doc_ids,
                            results=rerank_cache_data,
                        )
                        results = [results[r["index"]] for r in rerank_results]
                        logger.info(f"Reranked to top {len(results)} results")
                    except Exception as e:
                        logger.warning(
                            f"Rerank failed ({type(e).__name__}: {e}), "
                            f"using base retrieval results ({len(results)} docs)"
                        )
                        scores["rerank_fallback"] = 1.0

            await self.cache_service.store_search_results(query_vector, filters, results)
        else:
            scores["search_cache_hit"] = 1.0
        search_ms = (time.perf_counter() - t_search) * 1000
        metrics.record("qdrant_search", search_ms)
        logger.info("qdrant_search+rerank: %.0fms", search_ms)

        scores["results_count"] = float(len(results)) if results else 0.0
        logger.info(f"Found {len(results)} results")

        if not results:
            scores["no_results"] = 1.0
            await message.answer(
                "Ничего не нашел по вашему запросу.\n\nПопробуйте переформулировать запрос."
            )
            return

        # 5. Small-to-big context expansion (optional)
        results_for_llm = results
        if self.config.small_to_big_mode in ("on", "auto"):
            should_expand = self.config.small_to_big_mode == "on" or (
                self.config.small_to_big_mode == "auto" and query_type == QueryType.COMPLEX
            )
            if should_expand:
                expanded = await self.small_to_big_service.expand_context(
                    chunks=results,
                    window_before=self.config.small_to_big_window_before,
                    window_after=self.config.small_to_big_window_after,
                )
                results_for_llm = [
                    {
                        "text": ec.expanded_text,
                        "metadata": ec.original_chunk.get("metadata", {}),
                        "score": ec.original_chunk.get("score", 0.0),
                    }
                    for ec in expanded
                ]
                logger.info(f"Small-to-big expanded to {len(results_for_llm)} chunks")

        # 6. Get conversation history for context-aware responses
        _conversation_history = await self.cache_service.get_conversation_history(user_id, last_n=3)

        # Store user query in conversation
        await self.cache_service.store_conversation_message(user_id, "user", query)

        scores["llm_used"] = 1.0
        t_llm = time.perf_counter()

        # 7. Generate answer with LLM
        temp_message = await message.answer("Генерирую ответ...")

        # Confidence scoring mode (non-streaming, returns ConfidenceResult)
        if self.config.enable_confidence_scoring:
            result = await self.llm_service.generate_answer(
                query, results_for_llm, with_confidence=True
            )
            scores["confidence_score"] = result.confidence

            if result.is_low_confidence:
                logger.info(f"Low confidence ({result.confidence:.2f}), using fallback response")
                answer = self.llm_service.get_low_confidence_response(
                    query, results_for_llm, result.confidence
                )
            else:
                answer = result.answer

            try:
                await temp_message.edit_text(answer, parse_mode="Markdown")
            except Exception:
                await temp_message.edit_text(answer)

        else:
            # Standard streaming mode
            accumulated_text = ""
            last_sent_text = ""
            chunk_count = 0

            try:
                async for chunk in self.llm_service.stream_answer(
                    question=query,
                    context_chunks=results_for_llm,
                ):
                    accumulated_text += chunk
                    chunk_count += 1

                    if (
                        chunk_count % 10 == 0 or chunk in ".!?\n"
                    ) and accumulated_text != last_sent_text:
                        try:
                            await temp_message.edit_text(accumulated_text)
                            last_sent_text = accumulated_text
                        except Exception as edit_err:
                            logger.debug("Streaming edit skipped: %s", edit_err)

                # Final update with complete answer (only if different)
                if accumulated_text != last_sent_text:
                    try:
                        await temp_message.edit_text(accumulated_text, parse_mode="Markdown")
                    except Exception:
                        await temp_message.edit_text(accumulated_text)
                answer = accumulated_text

                # Empty stream fallback: if streaming yielded nothing, use sync generation
                if not answer.strip():
                    logger.warning(
                        "Stream returned empty response, falling back to generate_answer"
                    )
                    answer = await self.llm_service.generate_answer(query, results_for_llm)
                    try:
                        await temp_message.edit_text(answer, parse_mode="Markdown")
                    except Exception:
                        await temp_message.edit_text(answer)

            except Exception as e:
                logger.error(f"Streaming error: {e}", exc_info=True)
                answer = await self.llm_service.generate_answer(query, results_for_llm)
                try:
                    await temp_message.edit_text(answer, parse_mode="Markdown")
                except Exception:
                    await temp_message.edit_text(answer)

        llm_ms = (time.perf_counter() - t_llm) * 1000
        metrics.record("llm_generate", llm_ms)
        logger.info("llm_generate: %.0fms", llm_ms)

        # 8. Store assistant answer in conversation
        await self.cache_service.store_conversation_message(user_id, "assistant", answer)

        # 9. Fire-and-forget: store in semantic cache with pre-computed vector
        def _log_store_error(task: asyncio.Task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.warning("Semantic cache store failed: %s: %s", type(exc).__name__, exc)

        store_task = asyncio.create_task(
            self.cache_service.store_semantic_cache(
                clean_query,
                answer,
                vector=query_vector,
                user_id=user_id,
                query_type=query_type.value,
                ttl=get_ttl_for_query(query, answer),
            )
        )
        store_task.add_done_callback(_log_store_error)

    async def _get_sparse_vector(self, text: str) -> dict:
        """Generate sparse vector via BGE-M3 API.

        Args:
            text: Query text

        Returns:
            Dict with 'indices' and 'values' for Qdrant sparse vector
        """
        if self._http_client is None:
            timeout = float(os.getenv("BGE_M3_TIMEOUT", "120.0"))
            self._http_client = httpx.AsyncClient(timeout=timeout)

        try:
            response = await self._http_client.post(
                f"{self.config.bge_m3_url}/encode/sparse",
                json={"texts": [text]},
            )
            response.raise_for_status()
            data = response.json()
            # BGE-M3 returns {"lexical_weights": [{"indices": [...], "values": [...]}]}
            weights = data.get("lexical_weights", [{}])
            if weights:
                return {
                    "indices": weights[0].get("indices", []),
                    "values": weights[0].get("values", []),
                }
            return {"indices": [], "values": []}
        except Exception as e:
            logger.warning(f"BGE-M3 sparse error: {e}, returning empty sparse vector")
            return {"indices": [], "values": []}

    def _format_results(self, results: list[dict]) -> str:
        """Format search results for display."""
        formatted = []

        for i, result in enumerate(results[:3], 1):  # Show top 3
            meta = result.get("metadata", {})
            score = result.get("score", 0)

            text = f"{i}. {meta.get('title', 'N/A')}\n"

            # Format price with thousands separator if it's a number
            price = meta.get("price", "N/A")
            if isinstance(price, (int, float)):
                text += f"   💰 {price:,}€\n"
            else:
                text += f"   💰 {price}€\n"

            if "city" in meta:
                text += f"   📍 {meta['city']}\n"
            if "rooms" in meta:
                text += f"   🛏 {meta['rooms']} комн.\n"
            if "area" in meta:
                text += f"   📐 {meta['area']} м²\n"
            if "distance_to_sea" in meta:
                text += f"   🌊 {meta['distance_to_sea']} м до моря\n"

            text += f"   ⭐ Релевантность: {score:.2f}"

            formatted.append(text)

        return "\n\n".join(formatted)

    async def start(self):
        """Start bot polling."""
        logger.info("Starting bot...")

        # Initialize cache at startup (loads HF model, may take time on first run)
        if not self._cache_initialized:
            logger.info("Initializing cache service...")
            await self.cache_service.initialize()
            self._cache_initialized = True
            logger.info("Cache service ready")

        # Preflight dependency checks (raises PreflightError for CRITICAL failures)
        from .preflight import check_dependencies

        await check_dependencies(self.config)

        # Start Redis health monitor (background task, every 5 min)
        await self._redis_monitor.start()

        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")
        await self._redis_monitor.stop()
        await self.cache_service.close()
        await self.query_analyzer.close()
        await self.llm_service.close()
        await self.qdrant_service.close()
        if self.hyde_generator:
            await self.hyde_generator.close()
        if self._http_client:
            await self._http_client.aclose()
        # Close provider services (if they have close method and aren't VoyageService)
        if hasattr(self.dense_service, "close") and self.dense_service is not self.voyage_service:
            await self.dense_service.close()
        if (
            self.rerank_service is not None
            and hasattr(self.rerank_service, "close")
            and self.rerank_service is not self.voyage_service
        ):
            await self.rerank_service.close()
        await self.bot.session.close()
