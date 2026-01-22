"""Main Telegram bot logic."""

import contextlib
import logging

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from .config import BotConfig
from .middlewares import setup_error_middleware, setup_throttling_middleware
from .services import (
    CacheService,
    CESCPersonalizer,
    LLMService,
    QdrantService,
    QueryAnalyzer,
    UserContextService,
    VoyageService,
)


logger = logging.getLogger(__name__)


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
        ***REMOVED*** AI unified service (embeddings + reranker)
        # Asymmetric retrieval: voyage-4-large for docs, voyage-4-lite for queries
        self.voyage_service = VoyageService(
            api_key=config.voyage_api_key,
            model_docs=config.voyage_model_docs,
            model_queries=config.voyage_model_queries,
            model_rerank=config.voyage_model_rerank,
        )
        ***REMOVED*** service with hybrid search, score boosting, MMR
        self.qdrant_service = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
        )

        # BM42 sparse embedding service (HTTP client)
        self.bm42_url = config.bm42_url
        self._http_client: httpx.AsyncClient | None = None
        self.llm_service = LLMService(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
        )

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

        # Track initialization state
        self._cache_initialized = False

        # Setup middlewares (before handlers)
        self._setup_middlewares()

        # Register handlers
        self._register_handlers()

    def _setup_middlewares(self):
        """Setup bot middlewares."""
        # Rate limiting: 1.5 seconds between requests
        setup_throttling_middleware(self.dp, rate_limit=1.5, admin_ids=[])

        # Error handling middleware
        setup_error_middleware(self.dp)

        logger.info("Middlewares configured")

    def _register_handlers(self):
        """Register message handlers."""
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("help"))(self.cmd_help)
        self.dp.message(Command("clear"))(self.cmd_clear)
        self.dp.message(Command("stats"))(self.cmd_stats)
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

    async def handle_query(self, message: Message):
        """Handle user query with multi-level caching RAG pipeline."""
        query = message.text
        user_id = message.from_user.id
        logger.info(f"Query from {user_id}: {query}")

        # CESC: Update user context (extracts preferences every Nth query)
        if self.config.cesc_enabled:
            await self.user_context_service.update_from_query(user_id, query)

        # Initialize cache on first query if not done yet
        if not self._cache_initialized:
            await self.cache_service.initialize()
            self._cache_initialized = True

        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, "typing")

        # 1. Generate embedding (with embeddings cache - Tier 1)
        query_vector = await self.cache_service.get_cached_embedding(query)
        if query_vector is None:
            query_vector = await self.voyage_service.embed_query(query)
            await self.cache_service.store_embedding(query, query_vector)
            logger.info(f"Generated embedding: {len(query_vector)}-dim")
        else:
            logger.info(f"✓ Using cached embedding: {len(query_vector)}-dim")

        # 2. Check semantic cache (Tier 1 - highest priority)
        # Uses langcache-embed-v1 (256-dim) for fast cache matching
        cached_answer = await self.cache_service.check_semantic_cache(query)
        if cached_answer:
            # CESC: Personalize if enabled and user has preferences
            if self.config.cesc_enabled:
                user_context = await self.user_context_service.get_context(user_id)
                if self.cesc_personalizer.should_personalize(user_context):
                    cached_answer = await self.cesc_personalizer.personalize(
                        cached_response=cached_answer,
                        user_context=user_context,
                        query=query,
                    )
            await message.answer(cached_answer, parse_mode="Markdown")
            self.cache_service.log_metrics()
            return

        # 3. Analyze query with cache (Tier 2)
        analysis = await self.cache_service.get_cached_analysis(query)
        if analysis is None:
            analysis = await self.query_analyzer.analyze(query)
            await self.cache_service.store_analysis(query, analysis)

        filters = analysis.get("filters", {})
        semantic_query = analysis.get("semantic_query", query)
        logger.info(f"QueryAnalyzer: filters={filters}, semantic_query={semantic_query}")

        # 4. Search in Qdrant with hybrid search
        results = await self.cache_service.get_cached_search(query_vector, filters)
        if results is None:
            # Generate sparse vector for hybrid search
            sparse_vector = await self._get_sparse_vector(query)

            # Hybrid RRF search (dense + sparse)
            results = await self.qdrant_service.hybrid_search_rrf(
                dense_vector=query_vector,
                sparse_vector=sparse_vector,
                filters=filters if filters else None,
                top_k=self.config.search_top_k,
                dense_weight=self.config.hybrid_dense_weight,
                sparse_weight=self.config.hybrid_sparse_weight,
            )

            # MMR diversity reranking (if enabled and enough results)
            if self.config.mmr_enabled and len(results) > self.config.rerank_top_k:
                # Get embeddings for MMR calculation
                result_embeddings = [
                    await self.voyage_service.embed_query(r["text"])
                    for r in results[:20]  # Limit for performance
                ]
                results = self.qdrant_service.mmr_rerank(
                    points=results[:20],
                    embeddings=result_embeddings,
                    lambda_mult=self.config.mmr_lambda,
                    top_k=self.config.rerank_top_k * 2,
                )

            ***REMOVED*** rerank for final precision
            if results and len(results) > 1:
                doc_texts = [r["text"] for r in results]
                rerank_results = await self.voyage_service.rerank(
                    query=query,
                    documents=doc_texts,
                    top_k=self.config.rerank_top_k,
                )
                results = [results[r["index"]] for r in rerank_results]
                logger.info(f"Reranked to top {len(results)} results")

            await self.cache_service.store_search_results(query_vector, filters, results)

        logger.info(f"Found {len(results)} results")

        if not results:
            await message.answer(
                "😔 Ничего не нашел по вашему запросу.\n\nПопробуйте переформулировать запрос."
            )
            return

        # 5. Get conversation history for context-aware responses
        _conversation_history = await self.cache_service.get_conversation_history(user_id, last_n=3)

        # Store user query in conversation
        await self.cache_service.store_conversation_message(user_id, "user", query)

        # 6. Generate answer with LLM STREAMING
        temp_message = await message.answer("🔍 Генерирую ответ...")
        accumulated_text = ""
        last_sent_text = ""  # Track what we last sent
        chunk_count = 0

        try:
            async for chunk in self.llm_service.stream_answer(
                question=query,
                context_chunks=results,
            ):
                accumulated_text += chunk
                chunk_count += 1

                # Update message every 10 chunks or when punctuation appears
                # Only if text actually changed
                if (
                    chunk_count % 10 == 0 or chunk in ".!?\n"
                ) and accumulated_text != last_sent_text:
                    with contextlib.suppress(Exception):
                        await temp_message.edit_text(accumulated_text)
                        last_sent_text = accumulated_text

            # Final update with complete answer (only if different)
            if accumulated_text != last_sent_text:
                await temp_message.edit_text(accumulated_text, parse_mode="Markdown")
            answer = accumulated_text

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            # Fallback to non-streaming
            answer = await self.llm_service.generate_answer(query, results)
            await temp_message.edit_text(answer, parse_mode="Markdown")

        # 7. Store assistant answer in conversation
        await self.cache_service.store_conversation_message(user_id, "assistant", answer)

        # 8. Store in semantic cache for future queries
        # Uses langcache-embed-v1 (256-dim) for cache indexing
        await self.cache_service.store_semantic_cache(query, answer)

        # Log cache metrics
        self.cache_service.log_metrics()

    async def _get_sparse_vector(self, text: str) -> dict:
        """Generate BM42 sparse vector via HTTP service.

        Args:
            text: Query text

        Returns:
            Dict with 'indices' and 'values' for Qdrant sparse vector
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)

        try:
            response = await self._http_client.post(
                f"{self.bm42_url}/embed",
                json={"text": text},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"BM42 service error: {e}, returning empty sparse vector")
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

        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")
        await self.cache_service.close()
        await self.query_analyzer.close()
        await self.llm_service.close()
        await self.qdrant_service.close()
        if self._http_client:
            await self._http_client.aclose()
        await self.bot.session.close()
