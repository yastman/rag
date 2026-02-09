"""Main Telegram bot logic — LangGraph pipeline."""

import hashlib
import logging
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from .config import BotConfig
from .graph.config import GraphConfig
from .graph.graph import build_graph
from .graph.state import make_initial_state
from .middlewares import setup_error_middleware, setup_throttling_middleware
from .observability import get_client, observe, propagate_attributes
from .services.metrics import PipelineMetrics
from .services.redis_monitor import RedisHealthMonitor


logger = logging.getLogger(__name__)


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
    """Telegram bot for domain-specific search (configurable via BOT_DOMAIN)."""

    def __init__(self, config: BotConfig):
        """Initialize bot with services."""
        self.config = config
        self.bot = Bot(token=config.telegram_token)
        self.dp = Dispatcher()

        # Graph config for service factories
        self._graph_config = GraphConfig(
            llm_base_url=config.llm_base_url,
            llm_api_key=config.llm_api_key,
            llm_model=config.llm_model,
            bge_m3_url=config.bge_m3_url,
            qdrant_url=config.qdrant_url,
            qdrant_collection=config.qdrant_collection,
            search_top_k=config.search_top_k,
            redis_url=config.redis_url,
            domain=config.domain,
            domain_language=config.domain_language,
        )

        # Initialize LangGraph service dependencies
        from .integrations.cache import CacheLayerManager
        from .integrations.embeddings import BGEM3Embeddings, BGEM3SparseEmbeddings
        from .services.qdrant import QdrantService

        self._cache = CacheLayerManager(redis_url=config.redis_url)
        self._embeddings = BGEM3Embeddings(
            base_url=config.bge_m3_url,
        )
        self._sparse = BGEM3SparseEmbeddings(
            base_url=config.bge_m3_url,
        )
        self._qdrant = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
            quantization_mode=config.qdrant_quantization_mode,
        )

        # Rerank provider (feature flag)
        self._reranker = None
        if config.rerank_provider == "colbert":
            from .services.colbert_reranker import ColbertRerankerService

            self._reranker = ColbertRerankerService(base_url=config.bge_m3_url)
            logger.info("Using ColbertRerankerService for reranking")
        elif config.rerank_provider == "none":
            logger.info("Reranking disabled")

        # LLM (optional, defaults via GraphConfig.create_llm)
        self._llm = self._graph_config.create_llm()

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
        setup_throttling_middleware(self.dp, rate_limit=1.5, admin_ids=self.config.admin_ids)
        setup_error_middleware(self.dp)
        logger.info("Middlewares configured")

    def _register_handlers(self):
        """Register message handlers."""
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("help"))(self.cmd_help)
        self.dp.message(Command("clear"))(self.cmd_clear)
        self.dp.message(Command("stats"))(self.cmd_stats)
        self.dp.message(Command("metrics"))(self.cmd_metrics)
        self.dp.message(F.text)(self.handle_query)

    async def cmd_start(self, message: Message):
        """Handle /start command."""
        domain = self.config.domain
        await message.answer(
            f"Привет! Я бот-помощник по теме: {domain}.\n\n"
            "Задавай вопросы вроде:\n"
            "- Покажи квартиры дешевле 100 000 евро\n"
            "- 3-комнатные в Солнечный берег\n"
            "- Студии до 350м от моря\n\n"
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
        await self._cache.clear_conversation(user_id)
        await message.answer("✅ История диалога очищена.")

    async def cmd_stats(self, message: Message):
        """Handle /stats command - show cache statistics."""
        stats = self._cache.get_metrics()
        lines = ["📊 Статистика кеша:\n"]
        for tier, data in stats.items():
            hit_rate = data.get("hit_rate", 0)
            lines.append(
                f"• {tier}: {hit_rate:.0f}% ({data.get('hits', 0)}/{data.get('total', 0)})"
            )
        await message.answer("\n".join(lines))

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_ids

    async def cmd_metrics(self, message: Message):
        """Handle /metrics command - show pipeline p50/p95 timing stats."""
        metrics = PipelineMetrics.get()
        text = f"```\n{metrics.format_text()}\n```"
        await message.answer(text, parse_mode="Markdown")

    @observe(name="telegram-rag-query")
    async def handle_query(self, message: Message):
        """Handle user query via LangGraph RAG pipeline."""
        # Early typing ACK — user sees "typing..." immediately
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

        state = make_initial_state(
            user_id=message.from_user.id,
            session_id=make_session_id("chat", message.chat.id),
            query=message.text or "",
        )

        with propagate_attributes(
            session_id=state["session_id"],
            user_id=str(state["user_id"]),
            tags=["telegram", "rag"],
        ):
            graph = build_graph(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
                message=message,
            )

            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
                result = await graph.ainvoke(state)

            # Update trace with input/output and metadata
            lf = get_client()
            lf.update_current_trace(
                input={"query": message.text},
                output={"response": result.get("response", "")},
                metadata={
                    "query_type": result.get("query_type", ""),
                    "cache_hit": result.get("cache_hit", False),
                    "search_results_count": result.get("search_results_count", 0),
                    "rerank_applied": result.get("rerank_applied", False),
                },
            )

    async def start(self):
        """Start bot polling."""
        logger.info("Starting bot...")

        # Initialize cache at startup
        if not self._cache_initialized:
            logger.info("Initializing cache service...")
            await self._cache.initialize()
            self._cache_initialized = True
            logger.info("Cache service ready")

        # Preflight dependency checks
        from .preflight import check_dependencies

        await check_dependencies(self.config)

        # Start Redis health monitor (background task, every 5 min)
        await self._redis_monitor.start()

        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")
        await self._redis_monitor.stop()
        await self._cache.close()
        await self._qdrant.close()
        if self._reranker and hasattr(self._reranker, "close"):
            await self._reranker.close()
        await self.bot.session.close()
