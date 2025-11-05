"""Main Telegram bot logic."""

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from .config import BotConfig
from .services import CacheService, EmbeddingService, LLMService, QueryAnalyzer, RetrieverService


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
            model="gpt-4o-mini",  # Cost-efficient model for filter extraction
        )
        self.embedding_service = EmbeddingService(config.bge_m3_url)
        self.retriever_service = RetrieverService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
        )
        self.llm_service = LLMService(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
        )

        # Track initialization state
        self._cache_initialized = False

        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register message handlers."""
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("help"))(self.cmd_help)
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
            "• Студия дешевле 60000\n"
        )

    async def handle_query(self, message: Message):
        """Handle user query with multi-level caching RAG pipeline."""
        try:
            query = message.text
            logger.info(f"Query from {message.from_user.id}: {query}")

            # Initialize cache on first query if not done yet
            if not self._cache_initialized:
                await self.cache_service.initialize()
                self._cache_initialized = True

            # Show typing indicator
            await message.bot.send_chat_action(message.chat.id, "typing")

            # 1. Generate embedding (with embeddings cache - Tier 1)
            query_vector = await self.cache_service.get_cached_embedding(query)
            if query_vector is None:
                query_vector = await self.embedding_service.embed_query(query)
                await self.cache_service.store_embedding(query, query_vector)
                logger.info(f"Generated embedding: {len(query_vector)}-dim")
            else:
                logger.info(f"✓ Using cached embedding: {len(query_vector)}-dim")

            # 2. Check semantic cache (Tier 1 - highest priority)
            cached_answer = await self.cache_service.check_semantic_cache(query_vector)
            if cached_answer:
                await message.answer(cached_answer)
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

            # 4. Search in Qdrant with cache (Tier 2)
            results = await self.cache_service.get_cached_search(query_vector, filters)
            if results is None:
                results = self.retriever_service.search(
                    query_vector=query_vector,
                    filters=filters if filters else None,
                    top_k=self.config.top_k,
                    min_score=self.config.min_score,
                )
                await self.cache_service.store_search_results(query_vector, filters, results)

            logger.info(f"Found {len(results)} results")

            if not results:
                await message.answer(
                    "😔 Ничего не нашел по вашему запросу.\n\n"
                    "Попробуйте переформулировать запрос."
                )
                return

            # 5. Generate answer with LLM
            await message.bot.send_chat_action(message.chat.id, "typing")
            answer = await self.llm_service.generate_answer(
                question=query,
                context_chunks=results,
            )

            # 6. Store in semantic cache for future queries
            await self.cache_service.store_semantic_cache(query, query_vector, answer)

            # 7. Send answer
            await message.answer(answer)

            # Log cache metrics
            self.cache_service.log_metrics()

        except Exception as e:
            logger.error(f"Error handling query: {e}", exc_info=True)
            await message.answer(
                f"❌ Произошла ошибка при обработке запроса:\n{type(e).__name__}: {e}"
            )

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
        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")
        await self.cache_service.close()
        await self.query_analyzer.close()
        await self.embedding_service.close()
        await self.llm_service.close()
        await self.bot.session.close()
