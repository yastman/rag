"""Main Telegram bot logic — LangGraph pipeline."""

import asyncio
import contextlib
import hashlib
import inspect
import io
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.chat_action import ChatActionSender

from .agents.agent import create_bot_agent
from .agents.context import BotContext
from .config import BotConfig
from .graph.config import GraphConfig
from .graph.graph import build_graph
from .graph.nodes.cache import CACHEABLE_QUERY_TYPES
from .graph.nodes.classify import classify_query
from .graph.nodes.guard import _BLOCKED_RESPONSE, detect_injection
from .graph.state import make_initial_state
from .middlewares import setup_error_middleware, setup_throttling_middleware
from .observability import (
    create_callback_handler,
    get_client,
    get_langfuse_client,
    observe,
    propagate_attributes,
)
from .pipelines.client import _NO_RAG_QUERY_TYPES, _split_telegram_response, run_client_pipeline
from .scoring import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_history_scores,
    write_langfuse_scores,
)
from .services.history_service import HistoryService
from .services.manager_menu import render_start_menu
from .services.metrics import PipelineMetrics
from .services.redis_monitor import RedisHealthMonitor


logger = logging.getLogger(__name__)

# --- Checkpoint namespace constants (versioned for safe migration) ---
_CHECKPOINT_NS_VOICE = "tg:voice:v1"
_FEEDBACK_CONFIRMATION_TTL_S = 5.0


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


def _supervisor_thread_id(chat_id: int | str) -> str:
    """Build checkpointer thread id for text-agent conversations."""
    return f"tg_{chat_id}"


async def _delete_checkpointer_thread(checkpointer: Any, thread_id: str) -> None:
    """Delete checkpointer thread via async or sync SDK API."""
    adelete_thread = getattr(checkpointer, "adelete_thread", None)
    if callable(adelete_thread):
        await adelete_thread(thread_id)
        return

    delete_thread = getattr(checkpointer, "delete_thread", None)
    if callable(delete_thread):
        result = delete_thread(thread_id)
        if inspect.isawaitable(result):
            await result
        return

    raise AttributeError("checkpointer does not expose delete_thread/adelete_thread")


def _extract_current_turn(messages: list[Any]) -> list[Any]:
    """Extract current-turn messages from full checkpointer history (#507).

    Agent checkpointer returns full conversation history across turns.
    For per-turn scoring we only need messages after the last HumanMessage.
    """
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if getattr(messages[i], "type", None) == "human":
            last_human_idx = i
            break
    if last_human_idx < 0:
        return messages
    return messages[last_human_idx:]


def _build_trace_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Build shared metadata dict for Langfuse trace (text + voice handlers)."""
    return {
        "input_type": result.get("input_type", "text"),
        "query_type": result.get("query_type", ""),
        "cache_hit": result.get("cache_hit", False),
        "search_results_count": result.get("search_results_count", 0),
        "rerank_applied": result.get("rerank_applied", False),
        "llm_provider_model": result.get("llm_provider_model", ""),
        "llm_ttft_ms": result.get("llm_ttft_ms", 0.0),
        # Response length control (#129)
        "response_style": result.get("response_style"),
        "response_difficulty": result.get("response_difficulty"),
        "response_style_reasoning": result.get("response_style_reasoning"),
        "response_policy_mode": result.get("response_policy_mode"),
        "answer_words": result.get("answer_words"),
        "answer_to_question_ratio": result.get("answer_to_question_ratio"),
        # Voice transcription (#151)
        "stt_duration_ms": result.get("stt_duration_ms"),
        # Embedding resilience (#210)
        "embedding_error": result.get("embedding_error", False),
        "embedding_error_type": result.get("embedding_error_type"),
        # Conversation memory (#159)
        "memory_messages_count": len(result.get("messages", [])),
        "checkpointer_overhead_proxy_ms": result.get("checkpointer_overhead_proxy_ms"),
        # Voice post-pipeline cleanup diagnostics (#205)
        "pipeline_cleanup_error": result.get("pipeline_cleanup_error", False),
        "pipeline_cleanup_error_type": result.get("pipeline_cleanup_error_type"),
    }


def _write_voice_error_scores(
    lf: Any,
    *,
    trace_id: str = "",
    voice_duration_s: float | None = None,
    error_reason: str = "pipeline_error",
) -> None:
    """Write minimal Langfuse scores for voice traces that exit early (error paths).

    Ensures all voice traces have at least input_type and error context for dashboards.
    Uses explicit trace_id for score isolation (#435).
    """
    if not trace_id:
        trace_id = lf.get_current_trace_id()
    if not trace_id:
        return
    score(lf, trace_id, name="input_type", value="voice", data_type="CATEGORICAL")
    score(lf, trace_id, name="voice_error_reason", value=error_reason, data_type="CATEGORICAL")
    if voice_duration_s is not None:
        score(lf, trace_id, name="voice_duration_s", value=float(voice_duration_s))


def _is_post_pipeline_cleanup_error(exc: Exception) -> bool:
    """Best-effort detection for cleanup failures after graph nodes completed.

    LangGraph checkpointer/storage errors may surface during Pregel loop __aexit__
    after node execution and even after a response was already delivered.
    """
    message = str(exc).lower()
    cleanup_markers = (
        "asyncpregelloop.__aexit__",
        "pregelloop.__aexit__",
        "checkpointer",
        "pregel",
    )
    storage_markers = (
        "operationalerror",
        "redis.connectionerror",
        "consuming input failed",
        "connection lost",
        "connection closed",
        # RedisVL semantic cache errors (#524): index missing, schema mismatch,
        # RediSearch module not loaded on plain Redis instance
        "redisvlerror",
        "redissearcherror",
        "schemavalidationerror",
        "redisvl",
    )

    if any(m in message for m in cleanup_markers) and any(m in message for m in storage_markers):
        return True

    tb = exc.__traceback__
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename.lower()
        func = tb.tb_frame.f_code.co_name
        if "langgraph" in filename and func == "__aexit__":
            return True
        tb = tb.tb_next

    return False


def _is_checkpointer_runtime_error(exc: Exception) -> bool:
    """Detect runtime checkpointer/storage failures in text agent path."""
    message = str(exc).lower()
    checkpointer_markers = (
        "checkpointer",
        "checkpoint",
        "aput",
        "pregelloop.__aexit__",
        "asyncpregelloop.__aexit__",
    )
    storage_markers = (
        "serializ",
        "json",
        "msgpack",
        "redis",
        "connection",
    )
    if any(m in message for m in checkpointer_markers) and any(
        m in message for m in storage_markers
    ):
        return True

    tb = exc.__traceback__
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename.lower()
        if "langgraph" in filename and "checkpoint" in filename:
            return True
        tb = tb.tb_next
    return False


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
        from .integrations.embeddings import BGEM3HybridEmbeddings, BGEM3SparseEmbeddings
        from .services.qdrant import QdrantService

        self._cache = CacheLayerManager(redis_url=config.redis_url)
        self._hybrid = BGEM3HybridEmbeddings(
            base_url=config.bge_m3_url,
            timeout=self._graph_config.bge_m3_timeout,
        )
        # Use hybrid as primary embeddings provider
        self._embeddings = self._hybrid
        self._sparse = BGEM3SparseEmbeddings(
            base_url=config.bge_m3_url,
            timeout=self._graph_config.bge_m3_timeout,
        )
        self._qdrant = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name=config.qdrant_collection,
            quantization_mode=config.qdrant_quantization_mode,
            timeout=config.qdrant_timeout,
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
        self._llm_guard_client: Any | None = None
        if config.guard_ml_enabled:
            try:
                from .services.llm_guard_client import LLMGuardClient

                self._llm_guard_client = LLMGuardClient(base_url=config.llm_guard_url)
                logger.info("LLM guard ML classifier enabled: %s", config.llm_guard_url)
            except Exception:
                logger.exception(
                    "Failed to initialize LLM guard client; ML classifier will be disabled"
                )

        # Redis health monitor (periodic background task)
        self._redis_monitor = RedisHealthMonitor(redis_url=config.redis_url)

        # Conversation memory checkpointer (initialized in start())
        self._checkpointer: Any = None

        # Agent checkpointer — MemorySaver to avoid Redis JSON serialization
        # issues with LangChain Message objects (#420)
        self._agent_checkpointer: Any = None

        # History service (initialized in start())
        self._history_service: HistoryService | None = None

        # i18n hub (fluentogram) — initialized in start()
        self._i18n_hub: Any = None

        # User service (asyncpg) — initialized in start()
        self._user_service: Any = None

        # PostgreSQL pool — initialized in start()
        self._pg_pool: Any = None

        # Kommo CRM client (initialized in start() if enabled)
        self._kommo_client: Any | None = None

        # Lead scoring store (initialized in start() with pg_pool)
        self._lead_scoring_store: Any | None = None

        # Nurturing scheduler (initialized in start() if enabled)
        self._nurturing_scheduler: Any | None = None

        # Manager runtime services (initialized in start() if enabled)
        self._nurturing_service: Any | None = None
        self._funnel_analytics_service: Any | None = None

        # Hot lead notifier (initialized in start() when manager_ids configured)
        self._hot_lead_notifier: Any | None = None

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
        self.dp.message(Command("call"))(self.cmd_call)
        self.dp.message(Command("history"))(self.cmd_history)
        self.dp.message(Command("clearcache"))(self.cmd_clearcache)
        self.dp.message(F.voice)(self.handle_voice)
        self.dp.message(F.text)(self.handle_query)
        self.dp.callback_query(F.data.startswith("fb:"))(self.handle_feedback)
        self.dp.callback_query(F.data.startswith("hitl:"))(self.handle_hitl_callback)
        self.dp.callback_query(F.data.startswith("cc:"))(self.handle_clearcache_callback)

    async def _resolve_user_role(self, user_id: int) -> str:
        """Resolve user role from DB or config fallback (#388)."""
        db_role: str | None = None
        user_service = getattr(self, "_user_service", None)
        if user_service is not None and hasattr(user_service, "get_role"):
            try:
                resolved = await user_service.get_role(telegram_id=user_id)
                if isinstance(resolved, str):
                    normalized = resolved.strip().lower()
                    if normalized in {"manager", "client"}:
                        db_role = normalized
            except Exception:
                logger.warning("Role lookup failed", exc_info=True)

        # Config manager_ids should still elevate known managers even if DB is stale.
        if user_id in self.config.manager_ids:
            return "manager"
        return db_role or "client"

    async def cmd_start(self, message: Message, dialog_manager: Any = None):
        """Handle /start command — launch menu dialog (role-aware routing)."""
        assert message.from_user is not None
        role = await self._resolve_user_role(message.from_user.id)

        if dialog_manager is not None:
            from aiogram_dialog import StartMode

            from .dialogs.states import ClientMenuSG, ManagerMenuSG

            kommo_enabled = getattr(self.config, "kommo_enabled", False)
            if role == "manager" and kommo_enabled:
                await dialog_manager.start(ManagerMenuSG.main, mode=StartMode.RESET_STACK)
            else:
                await dialog_manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)
        else:
            # Fallback (dialog not initialized)
            await message.answer(render_start_menu(role=role, domain=self.config.domain))

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
        assert message.from_user is not None
        user_id = message.from_user.id
        checkpointer_cleared = True
        history_cleared = True
        text_thread_id = _supervisor_thread_id(message.chat.id)
        voice_thread_id = str(user_id)
        seen_checkpointers: set[int] = set()
        for cp_name, checkpointer in (
            ("conversation", self._checkpointer),
            ("agent", self._agent_checkpointer),
        ):
            if checkpointer is None:
                continue
            cp_id = id(checkpointer)
            if cp_id in seen_checkpointers:
                continue
            seen_checkpointers.add(cp_id)
            for thread_id in (text_thread_id, voice_thread_id):
                try:
                    await _delete_checkpointer_thread(checkpointer, thread_id)
                except Exception:
                    logger.warning(
                        "Failed to clear %s checkpointer thread %s",
                        cp_name,
                        thread_id,
                        exc_info=True,
                    )
                    checkpointer_cleared = False

        await self._cache.clear_conversation(user_id)

        if self._history_service is not None:
            try:
                history_cleared = bool(await self._history_service.delete_user_history(user_id))
            except Exception:
                logger.warning(
                    "Failed to clear Qdrant history for user_id=%s", user_id, exc_info=True
                )
                history_cleared = False

        if checkpointer_cleared and history_cleared:
            await message.answer("✅ История диалога очищена.")
        else:
            await message.answer(
                "⚠️ История очищена частично: локальный контекст сброшен, "
                "но долговременная память временно недоступна."
            )

    async def cmd_stats(self, message: Message):
        """Handle /stats command - show cache statistics."""
        stats = self._cache.get_metrics()
        lines = ["📊 Статистика кеша:\n"]
        for tier, data in stats.items():
            hit_rate = data.get("hit_rate", 0)
            hits = data.get("hits", 0)
            misses = data.get("misses", 0)
            total = hits + misses
            lines.append(f"• {tier}: {hit_rate:.0f}% ({hits}/{total})")
        await message.answer("\n".join(lines))

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_ids

    async def cmd_metrics(self, message: Message):
        """Handle /metrics command - show pipeline p50/p95 timing stats."""
        metrics = PipelineMetrics.get()
        text = f"```\n{metrics.format_text()}\n```"
        await message.answer(text, parse_mode="Markdown")

    async def cmd_clearcache(self, message: Message) -> None:
        """Handle /clearcache command — show inline keyboard to select cache tier for clearing."""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Semantic", callback_data="cc:semantic"),
                    InlineKeyboardButton(text="Embeddings", callback_data="cc:embeddings"),
                ],
                [
                    InlineKeyboardButton(text="Sparse", callback_data="cc:sparse"),
                    InlineKeyboardButton(text="Analysis", callback_data="cc:analysis"),
                ],
                [
                    InlineKeyboardButton(text="Search+Rerank", callback_data="cc:search"),
                    InlineKeyboardButton(text="Все", callback_data="cc:all"),
                ],
            ]
        )
        await message.answer("Выберите тип кеша для очистки:", reply_markup=keyboard)

    async def cmd_call(self, message: Message):
        """Handle /call command — trigger outbound voice call.

        Usage: /call +380501234567 [lead description]
        Admin-only command.
        """
        assert message.from_user is not None
        if not self._is_admin(message.from_user.id):
            await message.answer("Только администраторы могут инициировать звонки.")
            return

        if not self.config.livekit_url or not self.config.sip_trunk_id:
            await message.answer("Voice service не настроен (LIVEKIT_URL, SIP_TRUNK_ID).")
            return

        text = (message.text or "").strip()
        parts = text.split(maxsplit=2)  # /call +380... description
        if len(parts) < 2:
            await message.answer("Использование: /call +380501234567 [описание заявки]")
            return

        phone = parts[1]
        if not re.match(r"^\+?\d{10,15}$", phone):
            await message.answer("Неверный формат номера. Пример: +380501234567")
            return

        lead_desc = parts[2] if len(parts) > 2 else ""

        try:
            from livekit import api

            lk = api.LiveKitAPI(
                url=self.config.livekit_url,
                api_key=self.config.livekit_api_key,
                api_secret=self.config.livekit_api_secret,
            )

            try:
                room_name = f"voice-call-{uuid.uuid4().hex[:8]}"
                call_id = str(uuid.uuid4())

                # 1. Dispatch voice agent to room
                await lk.agent_dispatch.create_dispatch(
                    api.CreateAgentDispatchRequest(
                        agent_name="voice-bot",
                        room=room_name,
                        metadata=json.dumps(
                            {
                                "call_id": call_id,
                                "phone": phone,
                                "lead_data": {
                                    "description": lead_desc,
                                    "triggered_by": message.from_user.id,
                                },
                                "callback_chat_id": message.chat.id,
                            }
                        ),
                    )
                )

                # 2. Create SIP participant (dials the phone)
                await lk.sip.create_sip_participant(
                    api.CreateSIPParticipantRequest(
                        room_name=room_name,
                        sip_trunk_id=self.config.sip_trunk_id,
                        sip_call_to=phone,
                        participant_identity=f"phone-{phone}",
                        participant_name="Phone User",
                        krisp_enabled=True,
                        wait_until_answered=True,
                    )
                )

                await message.answer(
                    f"Звонок инициирован!\nID: `{call_id}`\nТелефон: {phone}\nRoom: {room_name}",
                    parse_mode="Markdown",
                )
            finally:
                await lk.aclose()

        except Exception:
            logger.exception("Failed to initiate call to %s", phone)
            await message.answer("Ошибка инициации звонка. Попробуйте позже.")

    @observe(name="telegram-history-search")
    async def cmd_history(self, message: Message):
        """Handle /history command — semantic search in conversation history."""
        search_start = time.perf_counter()
        assert message.from_user is not None
        user_id = message.from_user.id
        session_id = make_session_id("history", message.chat.id)

        text = (message.text or "").strip()
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.answer(
                "Использование: /history <запрос>\nПример: /history цены на квартиры"
            )
            return

        query = parts[1]

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "history"],
        ):
            lf = get_client()
            tid = lf.get_current_trace_id() or ""

            if self._history_service is None:
                lf.update_current_trace(
                    input={"command": "/history", "query": query},
                    output={"error": "service_unavailable"},
                    metadata={"user_id": user_id},
                )
                write_history_scores(lf, tid, count=0)
                await message.answer("История диалогов временно недоступна.")
                return

            try:
                results = await self._history_service.search_user_history(
                    user_id=user_id,
                    query=query,
                    limit=5,
                )
            except Exception:
                logger.exception("History search failed for user %s", user_id)
                lf.update_current_trace(
                    input={"command": "/history", "query": query},
                    output={"error": "backend_exception"},
                    metadata={"user_id": user_id},
                )
                write_history_scores(lf, tid, count=0)
                await message.answer("Произошла ошибка при поиске в истории. Попробуйте позже.")
                return

            search_ms = (time.perf_counter() - search_start) * 1000

            valid = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                q = r.get("query")
                resp = r.get("response")
                if not isinstance(q, str) or not isinstance(resp, str):
                    continue
                valid.append(r)

            lf.update_current_trace(
                input={"command": "/history", "query": query},
                output={"results_count": len(results), "valid_count": len(valid)},
                metadata={"user_id": user_id, "search_latency_ms": round(search_ms, 1)},
            )
            write_history_scores(
                lf,
                tid,
                count=len(valid),
                latency_ms=search_ms,
            )

            if not valid:
                await message.answer(f"По запросу «{query}» ничего не найдено в истории.")
                return

            lines = [f"📋 Найдено {len(valid)} записей:\n"]
            for i, r in enumerate(valid, 1):
                ts = r.get("timestamp", "")
                ts = ts[:16].replace("T", " ") if isinstance(ts, str) else ""
                lines.append(f"{i}. [{ts}]")
                lines.append(f"   В: {r['query']}")
                resp_preview = r["response"][:150]
                if len(r["response"]) > 150:
                    resp_preview += "..."
                lines.append(f"   О: {resp_preview}\n")

            await message.answer("\n".join(lines))

    @observe(name="telegram-rag-query")
    async def handle_query(self, message: Message, locale: str = "ru"):
        """Handle user query via supervisor graph (#310: supervisor-only)."""
        pipeline_start = time.perf_counter()
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        root_trace_metadata: dict[str, Any] = {}
        response_text = await self._handle_query_supervisor(
            message,
            pipeline_start,
            locale=locale,
            root_trace_metadata=root_trace_metadata,
        )
        update_kwargs: dict[str, Any] = {"output": {"response": response_text or ""}}
        if root_trace_metadata:
            update_kwargs["metadata"] = root_trace_metadata
        get_client().update_current_trace(**update_kwargs)

        # Update session last_active for idle detection (#445)
        if self._cache.redis is not None:
            try:
                await self._cache.redis.set(
                    f"session:last_active:{message.from_user.id}",
                    str(time.time()),
                    ex=7200,  # 2h TTL
                )
            except Exception:
                logger.debug("Failed to update session last_active", exc_info=True)

    async def _send_markdown_chunks(
        self,
        message: Message,
        text: str,
        *,
        reply_markup: Any | None = None,
    ) -> None:
        """Send long Telegram response in chunks with Markdown fallback."""
        chunks = list(_split_telegram_response(text))
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            markup = reply_markup if is_last else None
            try:
                await message.answer(chunk, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                logger.warning("Markdown parse failed in text path, falling back")
                try:
                    await message.answer(chunk, reply_markup=markup)
                except Exception:
                    logger.exception("Failed to send text response chunk")
                    await message.answer(chunk)

    async def _handle_client_direct_pipeline(
        self,
        *,
        message: Message,
        user_text: str,
        user_id: int,
        session_id: str,
        role: str,
        query_type: str,
        rag_result_store: dict[str, Any],
    ) -> str | None:
        """Thin wrapper: delegates to run_client_pipeline (see pipelines/client.py).

        Returns:
            Response text if the pipeline handled the request.
            None if the pipeline signals needs_agent=True (caller falls through to sdk_agent).
        """
        result = await run_client_pipeline(
            user_text=user_text,
            user_id=user_id,
            session_id=session_id,
            message=message,
            cache=self._cache,
            embeddings=self._embeddings,
            sparse_embeddings=self._sparse,
            qdrant=self._qdrant,
            reranker=self._reranker,
            llm=self._llm,
            config=self._graph_config,
            history_service=self._history_service,
            rag_result_store=rag_result_store,
            role=role,
            query_type=query_type,
        )
        if result.needs_agent:
            return None  # caller falls through to sdk_agent path
        return result.answer

    @observe(name="telegram-rag-supervisor")
    async def _handle_query_supervisor(
        self,
        message: Message,
        pipeline_start: float,
        locale: str = "ru",
        root_trace_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Handle query via create_agent SDK (#413 — replaces build_supervisor_graph)."""
        from .agents.agent import LOCALE_TO_LANGUAGE
        from .agents.history_tool import history_search
        from .agents.rag_tool import rag_search

        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        user_id = message.from_user.id
        session_id = make_session_id("chat", message.chat.id)
        role = await self._resolve_user_role(user_id)
        language = LOCALE_TO_LANGUAGE.get(locale, self.config.domain_language)

        rag_result_store: dict[str, Any] = {}

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "rag", "agent"],
        ):
            # --- Pre-agent content filter (#439) ---
            # Text path must run guard BEFORE agent.ainvoke() so that
            # injection attempts never reach the LLM at all.
            user_text = message.text or ""
            if self.config.content_filter_enabled:
                detected, risk_score, pattern = detect_injection(user_text)
                if detected:
                    if self.config.guard_mode == "hard":
                        logger.warning(
                            "Pre-agent guard blocked (score=%.2f, pattern=%s): %.80s",
                            risk_score,
                            pattern,
                            user_text,
                        )
                        await message.answer(_BLOCKED_RESPONSE)
                        lf = get_client()
                        tid = lf.get_current_trace_id() or ""
                        lf.update_current_trace(
                            input={"query": user_text},
                            output={"response": _BLOCKED_RESPONSE},
                            metadata={
                                "pipeline_mode": "sdk_agent",
                                "guard_blocked": True,
                                "injection_pattern": pattern,
                                "injection_risk_score": risk_score,
                            },
                        )
                        if tid:
                            score(
                                lf,
                                tid,
                                name="guard_blocked",
                                value=1,
                                data_type="BOOLEAN",
                            )
                            score(
                                lf,
                                tid,
                                name="injection_pattern",
                                value=pattern or "unknown",
                                data_type="CATEGORICAL",
                            )
                        if root_trace_metadata is not None:
                            root_trace_metadata.update(
                                {
                                    "pipeline_mode": "sdk_agent",
                                    "guard_blocked": True,
                                    "injection_pattern": pattern,
                                    "injection_risk_score": risk_score,
                                }
                            )
                        return _BLOCKED_RESPONSE
                    # soft/log mode: log but don't block
                    logger.warning(
                        "Pre-agent guard detected (mode=%s, score=%.2f, pattern=%s): %.80s",
                        self.config.guard_mode,
                        risk_score,
                        pattern,
                        user_text,
                    )

            # Pre-agent semantic cache check (#563) — skip agent entirely on HIT.
            # classify_query is ~0ms (regex-only). Embedding + check only for CACHEABLE types.
            query_type = classify_query(user_text)
            if query_type in CACHEABLE_QUERY_TYPES:
                try:
                    embedding = await self._embeddings.aembed_query(user_text)
                    await self._cache.store_embedding(user_text, embedding)
                    cached = await self._cache.check_semantic(
                        query=user_text,
                        vector=embedding,
                        query_type=query_type,
                        cache_scope="rag",
                        agent_role=role,
                    )
                    if cached:
                        logger.info("Pre-agent cache HIT (type=%s): %.60s", query_type, user_text)
                        rag_result_store["cache_hit"] = True
                        rag_result_store["query_type"] = query_type
                        rag_result_store["cache_key_embedding"] = embedding
                        # Write Langfuse scores and trace metadata
                        lf = get_client()
                        lf.update_current_trace(
                            input={"query": user_text},
                            output={"response": cached},
                            metadata={"pipeline_mode": "pre_agent_cache"},
                        )
                        tid = lf.get_current_trace_id() or ""
                        if tid:
                            score(lf, tid, name="pre_agent_cache_hit", value=1, data_type="BOOLEAN")
                            score(
                                lf,
                                tid,
                                name="query_type",
                                value=query_type,
                                data_type="CATEGORICAL",
                            )
                            score(lf, tid, name="user_role", value=role, data_type="CATEGORICAL")
                        # Build feedback keyboard (skip for non-RAG query types)
                        reply_markup = None
                        if tid and query_type not in _NO_RAG_QUERY_TYPES:
                            from telegram_bot.feedback import build_feedback_keyboard

                            reply_markup = build_feedback_keyboard(tid)
                        await self._send_markdown_chunks(
                            message,
                            str(cached),
                            reply_markup=reply_markup,
                        )
                        if root_trace_metadata is not None:
                            root_trace_metadata.update({"pipeline_mode": "pre_agent_cache"})
                        return cached
                    # MISS: stash embedding so rag_pipeline can skip recomputation
                    logger.debug("Pre-agent cache MISS (type=%s): %.60s", query_type, user_text)
                    rag_result_store["cache_key_embedding"] = embedding
                    rag_result_store["query_type"] = query_type
                except Exception:
                    logger.warning(
                        "Pre-agent cache check failed, proceeding to agent", exc_info=True
                    )

            if role == "client" and self.config.client_direct_pipeline_enabled:
                try:
                    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                        if root_trace_metadata is not None:
                            root_trace_metadata.update({"pipeline_mode": "client_direct"})
                        pipeline_answer = await self._handle_client_direct_pipeline(
                            message=message,
                            user_text=user_text,
                            user_id=user_id,
                            session_id=session_id,
                            role=role,
                            query_type=query_type,
                            rag_result_store=rag_result_store,
                        )
                        if pipeline_answer is not None:
                            return pipeline_answer
                        # needs_agent=True: fall through to sdk_agent path below
                except Exception:
                    logger.exception(
                        "Client direct pipeline failed; falling back to sdk_agent",
                    )

            # Build base tools list (client-only: rag_search)
            base_tools: list[Any] = [rag_search]

            manager_tools: list[Any] = []
            if role == "manager":
                from .agents.manager_tools import (
                    build_tools_for_role,
                    create_crm_score_sync_tool,
                    create_manager_nurturing_tools,
                )

                # history_search is manager-only: search past conversations with clients/deals
                if self._history_service is not None:
                    manager_tools.append(history_search)

                manager_tools.extend(
                    create_manager_nurturing_tools(
                        analytics_service=self._funnel_analytics_service,
                        nurturing_service=self._nurturing_service,
                    )
                )

                if self._lead_scoring_store is not None:
                    manager_tools.append(
                        create_crm_score_sync_tool(
                            scoring_store=self._lead_scoring_store,
                            kommo_client=getattr(self, "_kommo_client", None),
                            score_field_id=self.config.kommo_lead_score_field_id,
                            band_field_id=self.config.kommo_lead_band_field_id,
                        )
                    )

                # Add direct CRM tools conditionally
                if getattr(self.config, "kommo_enabled", False) and getattr(
                    self, "_kommo_client", None
                ):
                    from .agents.crm_tools import get_crm_tools

                    manager_tools.extend(get_crm_tools())

                tools = build_tools_for_role(
                    role=role,
                    base_tools=base_tools,
                    manager_tools=manager_tools,
                )
            else:
                tools = base_tools

            # Add utility tools for all roles (#445)
            from .agents.utility_tools import get_utility_tools

            tools.extend(get_utility_tools())

            # Create agent via SDK — route through LiteLLM proxy (#420)
            agent = create_bot_agent(
                model=self.config.supervisor_model,
                tools=tools,
                checkpointer=self._agent_checkpointer,
                language=language,
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                role=role,
                max_history_messages=self.config.agent_max_history_messages,
            )

            # Build context for tool DI
            ctx = BotContext(
                telegram_user_id=user_id,
                session_id=session_id,
                language=language,
                kommo_client=getattr(self, "_kommo_client", None),
                history_service=self._history_service,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                cache=self._cache,
                reranker=self._reranker,
                llm=self._llm,
                content_filter_enabled=self.config.content_filter_enabled,
                guard_mode=self.config.guard_mode,
                role=role,
                manager_id=(self.config.kommo_responsible_user_id if role == "manager" else None),
                history_relevance_threshold=self.config.history_relevance_threshold,
                original_query=message.text or "",
                original_user_query=message.text or "",
                bot=bot,
                manager_ids=list(self.config.manager_ids),
            )

            # Initialize handler inside propagation context so it inherits session/user/tags.
            langfuse_handler = create_callback_handler()
            callbacks = [langfuse_handler] if langfuse_handler else []
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                result = await self._ainvoke_supervisor_with_recovery(
                    agent=agent,
                    tools=tools,
                    role=role,
                    user_text=user_text,
                    chat_id=message.chat.id,
                    callbacks=callbacks,
                    bot_context=ctx,
                    rag_result_store=rag_result_store,
                )

            # Check for HITL interrupt (#443)
            interrupt_data = result.get("__interrupt__")
            if interrupt_data:
                interrupt_payload = interrupt_data[0].value
                await self._send_hitl_confirmation(
                    message=message,
                    payload=interrupt_payload,
                    thread_id=_supervisor_thread_id(message.chat.id),
                )
                return None

            # Extract response from final message
            messages = result.get("messages", [])
            response_text = ""
            if messages:
                last_msg = messages[-1]
                response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            # Extract LLM metrics from supervisor agent response (#515)
            if messages:
                last_ai = next(
                    (
                        m
                        for m in reversed(messages)
                        if hasattr(m, "response_metadata") and m.response_metadata
                    ),
                    None,
                )
                if last_ai:
                    token_usage = last_ai.response_metadata.get("token_usage", {}) or {}
                    decode_time = token_usage.get("completion_time")
                    if decode_time is not None and float(decode_time) > 0:
                        rag_result_store["llm_decode_ms"] = round(float(decode_time) * 1000, 1)
                        completion_tokens = token_usage.get("completion_tokens")
                        if completion_tokens and int(completion_tokens) > 0:
                            rag_result_store["llm_tps"] = round(
                                float(completion_tokens) / float(decode_time), 1
                            )
                    queue_time = token_usage.get("queue_time")
                    if queue_time is not None:
                        rag_result_store["llm_queue_ms"] = round(float(queue_time) * 1000, 1)

            # Send response with feedback buttons, sources, and Markdown (#426).
            # Skip if a tool already delivered the response via streaming (#428).
            if response_text and not ctx.response_sent:
                lf = get_client()
                trace_id = lf.get_current_trace_id() or ""
                query_type = rag_result_store.get("query_type", "")

                # Build feedback keyboard
                reply_markup = None
                if trace_id and query_type and query_type not in {"CHITCHAT", "OFF_TOPIC"}:
                    from telegram_bot.feedback import build_feedback_keyboard

                    reply_markup = build_feedback_keyboard(trace_id)

                # Fallback: history_search stores keyboard in BotContext side-channel (#434)
                if reply_markup is None and ctx.history_reply_markup is not None:
                    reply_markup = ctx.history_reply_markup

                # Build source attribution
                sources_text = ""
                documents = rag_result_store.get("documents", [])
                if (
                    self._graph_config.show_sources
                    and documents
                    and query_type
                    not in {
                        "CHITCHAT",
                        "OFF_TOPIC",
                    }
                ):
                    from telegram_bot.graph.nodes.respond import _MAX_SOURCES, format_sources

                    sources_text = format_sources(documents)
                    rag_result_store["sources_count"] = min(len(documents), _MAX_SOURCES)

                full_response = response_text + sources_text if sources_text else response_text

                # Send with Markdown, fallback to plain text
                chunks = list(_split_telegram_response(full_response))
                for i, chunk in enumerate(chunks):
                    is_last = i == len(chunks) - 1
                    markup = reply_markup if is_last else None
                    try:
                        await message.answer(chunk, parse_mode="Markdown", reply_markup=markup)
                    except Exception:
                        logger.warning("Markdown parse failed in text path, falling back")
                        try:
                            await message.answer(chunk, reply_markup=markup)
                        except Exception:
                            logger.exception("Failed to send text response chunk")
                            await message.answer(chunk)

            # Store final agent response in semantic cache for cacheable query types.
            # Use cache_key_embedding (original query embedding) so that future
            # check_semantic calls with the same user text can hit the cache
            # even when the agent reformulated the query for retrieval (#504).
            if self._cache and response_text:
                query_type = str(rag_result_store.get("query_type", "") or "")
                # Prefer cache_key_embedding (original query vector) over query_embedding
                # (retrieval/rewritten vector) to avoid check/store vector mismatch.
                store_vector = rag_result_store.get("cache_key_embedding") or rag_result_store.get(
                    "query_embedding"
                )
                if (
                    query_type in CACHEABLE_QUERY_TYPES
                    and not rag_result_store.get("cache_hit", False)
                    and isinstance(store_vector, list)
                    and bool(store_vector)
                ):
                    try:
                        await self._cache.store_semantic(
                            query=message.text or "",
                            response=response_text,
                            vector=store_vector,
                            query_type=query_type,
                            cache_scope="rag",
                            agent_role=role,
                        )
                    except Exception:
                        logger.warning("Failed to store semantic cache in text path", exc_info=True)

            # Wall-time for the full pipeline
            wall_ms = (time.perf_counter() - pipeline_start) * 1000

            # Write Langfuse trace metadata
            lf = get_client()
            lf.update_current_trace(
                input={"query": message.text},
                metadata={
                    "pipeline_mode": "sdk_agent",
                    "pipeline_wall_ms": wall_ms,
                },
            )
            if root_trace_metadata is not None:
                root_trace_metadata.update(
                    {
                        "pipeline_mode": "sdk_agent",
                        "pipeline_wall_ms": wall_ms,
                    }
                )
            tid = lf.get_current_trace_id() or ""
            if tid:
                lf.create_score(
                    trace_id=tid,
                    name="supervisor_model",
                    value=self.config.supervisor_model,
                    data_type="CATEGORICAL",
                    score_id=f"{tid}-supervisor_model",
                )
                # User role score (#388)
                lf.create_score(
                    trace_id=tid,
                    name="user_role",
                    value=role,
                    data_type="CATEGORICAL",
                    score_id=f"{tid}-user_role",
                )
                current_turn_msgs = _extract_current_turn(messages)
                # Tool call count (#374): count actual tool calls, not just messages.
                tool_calls = sum(
                    len(m.tool_calls)
                    for m in current_turn_msgs
                    if hasattr(m, "tool_calls") and isinstance(m.tool_calls, list) and m.tool_calls
                )
                if tool_calls > 0:
                    lf.create_score(
                        trace_id=tid,
                        name="tool_calls_total",
                        value=float(tool_calls),
                        score_id=f"{tid}-tool_calls_total",
                    )

                # CRM tool usage scores (#440)
                from telegram_bot.scoring import write_crm_scores

                write_crm_scores(lf, current_turn_msgs, trace_id=tid)
                # Overwrite sources_shown/sources_count with actual post-send values (#514)
                sources_count_actual = int(rag_result_store.get("sources_count", 0) or 0)
                if sources_count_actual > 0:
                    score(lf, tid, name="sources_shown", value=1, data_type="BOOLEAN")
                    score(lf, tid, name="sources_count", value=float(sources_count_actual))

            # Persist Q&A to history
            if self._history_service and response_text:
                try:
                    saved = await self._history_service.save_turn(
                        user_id=user_id,
                        session_id=session_id,
                        query=message.text or "",
                        response=response_text,
                        input_type="text",
                    )
                    if tid:
                        lf.create_score(
                            trace_id=tid,
                            name="history_save_success",
                            value=1 if saved else 0,
                            data_type="BOOLEAN",
                            score_id=f"{tid}-history_save_success",
                        )
                except Exception:
                    logger.warning("Failed to save history turn", exc_info=True)

        return response_text

    async def _ainvoke_supervisor_with_recovery(
        self,
        *,
        agent: Any,
        tools: list[Any],
        role: str,
        user_text: str,
        chat_id: int,
        callbacks: list[Any],
        bot_context: BotContext,
        rag_result_store: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke supervisor agent and retry once with MemorySaver on checkpointer failures."""
        payload = {"messages": [{"role": "user", "content": user_text}]}
        config = {
            "callbacks": callbacks,
            "configurable": {
                "thread_id": _supervisor_thread_id(chat_id),
                "bot_context": bot_context,
                "rag_result_store": rag_result_store,
                "role": role,
                "user_id": bot_context.telegram_user_id,
                "session_id": bot_context.session_id,
            },
        }
        try:
            result: dict[str, Any] = await agent.ainvoke(payload, config=config)
            return result
        except Exception as exc:
            if not _is_checkpointer_runtime_error(exc):
                raise
            if role in {"manager", "admin"}:
                # Manager toolsets include write-side effects (CRM/nurturing).
                # Retrying the full agent run can duplicate external actions.
                logger.exception(
                    "Supervisor ainvoke failed with checkpointer runtime error; "
                    "skip retry for role=%s to avoid duplicate side effects",
                    role,
                )
                raise
            logger.exception(
                "Supervisor ainvoke failed due to checkpointer runtime error; "
                "retrying once with MemorySaver"
            )

        from .integrations.memory import create_fallback_checkpointer

        self._agent_checkpointer = create_fallback_checkpointer()
        fallback_agent = create_bot_agent(
            model=self.config.supervisor_model,
            tools=tools,
            checkpointer=self._agent_checkpointer,
            language=self.config.domain_language,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
        )
        fallback_result: dict[str, Any] = await fallback_agent.ainvoke(payload, config=config)
        return fallback_result

    @observe(name="telegram-rag-voice")
    async def handle_voice(self, message: Message):
        """Handle voice message via Whisper STT + LangGraph RAG pipeline."""
        pipeline_start = time.perf_counter()
        assert message.bot is not None
        assert message.from_user is not None
        assert message.voice is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        # Download voice file into memory
        voice = message.voice
        file = await bot.get_file(voice.file_id)
        assert file.file_path is not None
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        voice_bytes = buf.getvalue()

        # Guard: Whisper API limit is 25 MB
        if len(voice_bytes) > 25 * 1024 * 1024:
            await message.answer("Голосовое сообщение слишком длинное. Максимум ~16 минут.")
            return

        state = make_initial_state(
            user_id=message.from_user.id,
            session_id=make_session_id("chat", message.chat.id),
            query="",  # will be set by transcribe_node
        )
        state["voice_audio"] = voice_bytes
        state["voice_duration_s"] = float(voice.duration)
        state["input_type"] = "voice"
        state["max_rewrite_attempts"] = self._graph_config.max_rewrite_attempts
        state["show_sources"] = self._graph_config.show_sources
        state["max_llm_calls"] = self.config.max_llm_calls

        with propagate_attributes(
            session_id=state["session_id"],
            user_id=str(state["user_id"]),
            tags=["telegram", "rag", "voice"],
        ):
            # Inject Langfuse trace_id INSIDE propagate_attributes (#277)
            lf_pre = get_client()
            state["trace_id"] = lf_pre.get_current_trace_id() or ""

            graph = build_graph(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
                message=message,
                checkpointer=self._agent_checkpointer,
                show_transcription=self.config.show_transcription,
                voice_language=self.config.voice_language,
                stt_model=self.config.stt_model,
                content_filter_enabled=self.config.content_filter_enabled,
                guard_mode=self.config.guard_mode,
                guard_ml_enabled=self.config.guard_ml_enabled,
                llm_guard_client=self._llm_guard_client,
            )

            invoke_config = {
                "configurable": {
                    "thread_id": str(message.from_user.id),
                    "checkpoint_ns": _CHECKPOINT_NS_VOICE,
                }
            }
            result: dict[str, Any] | None = None
            try:
                async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                    invoke_start = time.perf_counter()
                    result = await graph.ainvoke(state, config=invoke_config)
                    ainvoke_wall_ms = (time.perf_counter() - invoke_start) * 1000
                    result["checkpointer_overhead_proxy_ms"] = (
                        compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms)
                    )
            except ValueError as e:
                if "Empty transcription" in str(e):
                    await message.answer("Голосовое сообщение не содержит речи.")
                    try:
                        _write_voice_error_scores(
                            get_client(),
                            trace_id=state.get("trace_id", ""),
                            voice_duration_s=voice.duration,
                            error_reason="empty_transcription",
                        )
                    except Exception:
                        logger.debug("Failed to write voice error scores", exc_info=True)
                    return
                raise
            except Exception as e:
                if result is None:
                    # Checkpointer/storage cleanup can fail after nodes complete.
                    # In that case avoid sending a false "recognition failed" message.
                    if _is_post_pipeline_cleanup_error(e):
                        logger.warning(
                            "Voice pipeline cleanup failed after execution (no extra user error)",
                            exc_info=True,
                        )
                        # Preserve observability even without returned graph state.
                        result = {
                            "response": state.get("response", ""),
                            "stt_text": state.get("stt_text", ""),
                            "stt_duration_ms": state.get("stt_duration_ms"),
                            "input_type": "voice",
                            "voice_duration_s": float(voice.duration),
                            "latency_stages": state.get("latency_stages", {}),
                            "messages": state.get("messages", []),
                            "pipeline_cleanup_error": True,
                            "pipeline_cleanup_error_type": type(e).__name__,
                        }
                    # Pipeline never returned — genuine failure
                    else:
                        logger.exception("Voice pipeline failed (no result)")
                        await message.answer(
                            "Не удалось распознать голосовое сообщение. Попробуйте отправить текстом."
                        )
                        try:
                            _write_voice_error_scores(
                                get_client(),
                                trace_id=state.get("trace_id", ""),
                                voice_duration_s=voice.duration,
                                error_reason="pipeline_failure",
                            )
                        except Exception:
                            logger.debug("Failed to write voice error scores", exc_info=True)
                        return
                # Pipeline succeeded but post-invoke cleanup failed (#201)
                # Answer already delivered via streaming/respond — don't confuse user
                else:
                    logger.warning(
                        "Post-pipeline error in voice handler (answer already delivered)",
                        exc_info=True,
                    )

            result["pipeline_wall_ms"] = (time.perf_counter() - pipeline_start) * 1000
            # User-perceived latency excludes post-respond summarization
            summarize_s = result.get("latency_stages", {}).get("summarize", 0)
            result["user_perceived_wall_ms"] = result["pipeline_wall_ms"] - (summarize_s * 1000)

            lf = get_client()
            tid = lf.get_current_trace_id() or ""
            try:
                lf.update_current_trace(
                    input={
                        "voice_duration_s": voice.duration,
                        "stt_text": result.get("stt_text", ""),
                    },
                    output={"response": result.get("response", "")},
                    metadata=_build_trace_metadata(result),
                )
            except Exception:
                logger.warning("Failed to update Langfuse voice trace metadata", exc_info=True)
            try:
                write_langfuse_scores(lf, result, trace_id=tid)
            except Exception:
                logger.warning("Failed to write Langfuse voice scores", exc_info=True)

            # Persist Q&A to history (fail-soft)
            if self._history_service and result.get("response"):
                try:
                    query_text = result.get("stt_text") or state.get("query", "")
                    saved = await self._history_service.save_turn(
                        user_id=message.from_user.id,
                        session_id=state["session_id"],
                        query=query_text,
                        response=result["response"],
                        input_type=result.get("input_type", "voice"),
                        query_embedding=result.get("query_embedding"),
                    )
                    if tid:
                        lf.create_score(
                            trace_id=tid,
                            name="history_save_success",
                            value=1 if saved else 0,
                            data_type="BOOLEAN",
                            score_id=f"{tid}-history_save_success",
                        )
                        lf.create_score(
                            trace_id=tid,
                            name="history_backend",
                            value="qdrant",
                            data_type="CATEGORICAL",
                            score_id=f"{tid}-history_backend",
                        )
                except Exception:
                    logger.warning("Failed to save voice history turn", exc_info=True)

            # Update session last_active for idle detection (#445)
            if self._cache.redis is not None:
                try:
                    await self._cache.redis.set(
                        f"session:last_active:{message.from_user.id}",
                        str(time.time()),
                        ex=7200,  # 2h TTL
                    )
                except Exception:
                    logger.debug("Failed to update session last_active", exc_info=True)

    async def _send_hitl_confirmation(
        self,
        message: Message,
        payload: dict,
        thread_id: str,
    ) -> None:
        """Send inline keyboard for HITL confirmation (#443)."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        preview = payload.get("preview", "Подтвердите операцию")

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Подтвердить", callback_data="hitl:approve"),
                    InlineKeyboardButton(text="Отменить", callback_data="hitl:cancel"),
                ]
            ]
        )

        await message.answer(
            f"Подтвердите действие:\n\n{preview}",
            reply_markup=keyboard,
        )

    @observe(name="telegram-hitl-callback")
    async def handle_hitl_callback(self, callback: CallbackQuery) -> None:
        """Handle HITL approve/cancel button click (#443)."""
        if callback.from_user is None or callback.message is None:
            await callback.answer()
            return

        data = callback.data or ""
        action = "approve" if data == "hitl:approve" else "cancel"
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id
        thread_id = _supervisor_thread_id(chat_id)

        await callback.answer("Принято" if action == "approve" else "Отменено")

        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)

        # Rebuild agent with same tools and checkpointer (mirrors _handle_query_supervisor)
        from .agents.rag_tool import rag_search
        from .agents.utility_tools import get_utility_tools

        role = await self._resolve_user_role(user_id)
        session_id = make_session_id("chat", chat_id)

        base_tools: list[Any] = [rag_search]
        manager_tools: list[Any] = []
        if role == "manager":
            from .agents.manager_tools import (
                build_tools_for_role,
                create_crm_score_sync_tool,
                create_manager_nurturing_tools,
            )

            if self._history_service is not None:
                from .agents.history_tool import history_search

                manager_tools.append(history_search)

            manager_tools.extend(
                create_manager_nurturing_tools(
                    analytics_service=self._funnel_analytics_service,
                    nurturing_service=self._nurturing_service,
                )
            )

            if self._lead_scoring_store is not None:
                manager_tools.append(
                    create_crm_score_sync_tool(
                        scoring_store=self._lead_scoring_store,
                        kommo_client=getattr(self, "_kommo_client", None),
                        score_field_id=self.config.kommo_lead_score_field_id,
                        band_field_id=self.config.kommo_lead_band_field_id,
                    )
                )

            if getattr(self.config, "kommo_enabled", False) and getattr(
                self, "_kommo_client", None
            ):
                from .agents.crm_tools import get_crm_tools

                manager_tools.extend(get_crm_tools())

            tools = build_tools_for_role(
                role=role, base_tools=base_tools, manager_tools=manager_tools
            )
        else:
            tools = base_tools

        tools.extend(get_utility_tools())

        agent = create_bot_agent(
            model=self.config.supervisor_model,
            tools=tools,
            checkpointer=self._agent_checkpointer,
            language=self.config.domain_language,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            role=role,
            max_history_messages=self.config.agent_max_history_messages,
        )

        ctx = BotContext(
            telegram_user_id=user_id,
            session_id=session_id,
            language=self.config.domain_language,
            kommo_client=getattr(self, "_kommo_client", None),
            history_service=self._history_service,
            embeddings=self._embeddings,
            sparse_embeddings=self._sparse,
            qdrant=self._qdrant,
            cache=self._cache,
            reranker=self._reranker,
            llm=self._llm,
            content_filter_enabled=self.config.content_filter_enabled,
            guard_mode=self.config.guard_mode,
            role=role,
            manager_id=(self.config.kommo_responsible_user_id if role == "manager" else None),
        )

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "hitl", "resume"],
        ):
            from langgraph.types import Command

            langfuse_handler = create_callback_handler()
            callbacks = [langfuse_handler] if langfuse_handler else []

            result = await agent.ainvoke(
                Command(resume={"action": action}),
                config={
                    "callbacks": callbacks,
                    "configurable": {
                        "thread_id": thread_id,
                        "bot_context": ctx,
                    },
                },
            )

        messages = result.get("messages", [])
        response_text = ""
        if messages:
            last_msg = messages[-1]
            response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        if response_text:
            bot = callback.message.bot
            for chunk in _split_telegram_response(response_text):
                await bot.send_message(chat_id=chat_id, text=chunk)

        lf = get_client()
        lf.score_current_trace(name="hitl_action", value=action, data_type="CATEGORICAL")

    async def handle_feedback(self, callback: CallbackQuery):
        """Handle feedback button callback (#229)."""
        from .feedback import build_feedback_confirmation, parse_feedback_callback

        data = callback.data or ""

        # Acknowledge "done" button silently
        if data == "fb:done":
            await callback.answer()
            return

        parsed = parse_feedback_callback(data)
        if parsed is None:
            await callback.answer()
            return

        value, trace_id = parsed
        user_id = callback.from_user.id if callback.from_user else 0

        await callback.answer("Спасибо за отзыв!")

        # Write score to Langfuse (direct client, not context-dependent)
        try:
            lf_client = get_langfuse_client()
            if lf_client is not None:
                lf_client.create_score(
                    trace_id=trace_id,
                    name="user_feedback",
                    value=value,
                    data_type="NUMERIC",
                    comment=f"user_id:{user_id}",
                    score_id=f"{trace_id}-user_feedback",
                )
        except Exception:
            logger.warning("Failed to write feedback score to Langfuse", exc_info=True)

        # Update keyboard to confirmation
        liked = value > 0
        try:
            msg = callback.message
            if msg is not None and hasattr(msg, "edit_reply_markup"):
                await msg.edit_reply_markup(reply_markup=build_feedback_confirmation(liked=liked))
                cleanup_task = asyncio.create_task(
                    self._clear_feedback_confirmation_later(msg, _FEEDBACK_CONFIRMATION_TTL_S)
                )
                cleanup_task.add_done_callback(lambda t: t.result() if not t.cancelled() else None)
        except Exception:
            logger.debug("Failed to update feedback keyboard", exc_info=True)

    async def _clear_feedback_confirmation_later(
        self, message: Any, delay_s: float = _FEEDBACK_CONFIRMATION_TTL_S
    ) -> None:
        """Clear feedback confirmation button after a short delay."""
        await asyncio.sleep(delay_s)
        try:
            await message.edit_reply_markup(reply_markup=None)
        except Exception:
            logger.debug("Failed to clear feedback confirmation keyboard", exc_info=True)

    async def handle_clearcache_callback(self, callback_query: CallbackQuery) -> None:
        """Handle /clearcache inline keyboard callbacks (cc: prefix)."""
        _TIER_NAMES = {
            "semantic": "Semantic cache",
            "embeddings": "Embeddings cache",
            "sparse": "Sparse embeddings cache",
            "analysis": "Analysis cache",
            "search": "Search + Rerank cache",
            "all": "Все кеши",
        }
        data = (callback_query.data or "").removeprefix("cc:")
        tier_name = _TIER_NAMES.get(data, data)
        try:
            if data == "all":
                result = await self._cache.clear_all_caches()
                lines = [
                    f"Очищено: {_TIER_NAMES.get(t, t)} — {n} ключей" for t, n in result.items()
                ]
                text = "\n".join(lines)
            elif data == "semantic":
                deleted = await self._cache.clear_semantic_cache()
                text = f"Очищено: {tier_name} — {deleted} ключей"
            else:
                deleted = await self._cache.clear_by_tier(data)
                text = f"Очищено: {tier_name} — {deleted} ключей"
        except Exception:
            logger.warning("Failed to clear cache tier: %s", data, exc_info=True)
            text = "Ошибка очистки кеша"

        await callback_query.answer()
        if callback_query.message is not None:
            await callback_query.message.edit_text(text)

    async def handle_menu_action(
        self, callback: CallbackQuery, query_text: str, locale: str = "ru"
    ) -> None:
        """Handle menu button click — dispatch query_text to agent pipeline.

        Called by on_click handlers in dialog files after manager.done().
        Reuses _ainvoke_supervisor_with_recovery for consistency with handle_query.
        """
        from .agents.agent import LOCALE_TO_LANGUAGE
        from .agents.rag_tool import rag_search

        if callback.from_user is None or callback.message is None:
            return

        user_id = callback.from_user.id
        chat_id = callback.message.chat.id
        bot = callback.message.bot

        role = await self._resolve_user_role(user_id)
        language = LOCALE_TO_LANGUAGE.get(locale, self.config.domain_language)
        session_id = make_session_id("chat", chat_id)

        # Build tools list (mirrors _handle_query_supervisor tool assembly)
        base_tools: list[Any] = [rag_search]
        manager_tools: list[Any] = []
        if role == "manager":
            from .agents.manager_tools import (
                build_tools_for_role,
                create_crm_score_sync_tool,
                create_manager_nurturing_tools,
            )

            if self._history_service is not None:
                from .agents.history_tool import history_search

                manager_tools.append(history_search)

            manager_tools.extend(
                create_manager_nurturing_tools(
                    analytics_service=self._funnel_analytics_service,
                    nurturing_service=self._nurturing_service,
                )
            )

            if self._lead_scoring_store is not None:
                manager_tools.append(
                    create_crm_score_sync_tool(
                        scoring_store=self._lead_scoring_store,
                        kommo_client=getattr(self, "_kommo_client", None),
                        score_field_id=self.config.kommo_lead_score_field_id,
                        band_field_id=self.config.kommo_lead_band_field_id,
                    )
                )

            if getattr(self.config, "kommo_enabled", False) and getattr(
                self, "_kommo_client", None
            ):
                from .agents.crm_tools import get_crm_tools

                manager_tools.extend(get_crm_tools())

            tools = build_tools_for_role(
                role=role,
                base_tools=base_tools,
                manager_tools=manager_tools,
            )
        else:
            tools = base_tools

        # Add utility tools for all roles (#445)
        from .agents.utility_tools import get_utility_tools

        tools.extend(get_utility_tools())

        agent = create_bot_agent(
            model=self.config.supervisor_model,
            tools=tools,
            checkpointer=self._agent_checkpointer,
            language=language,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            role=role,
            max_history_messages=self.config.agent_max_history_messages,
        )

        ctx = BotContext(
            telegram_user_id=user_id,
            session_id=session_id,
            language=language,
            kommo_client=getattr(self, "_kommo_client", None),
            history_service=self._history_service,
            embeddings=self._embeddings,
            sparse_embeddings=self._sparse,
            qdrant=self._qdrant,
            cache=self._cache,
            reranker=self._reranker,
            llm=self._llm,
            content_filter_enabled=self.config.content_filter_enabled,
            guard_mode=self.config.guard_mode,
            role=role,
            manager_id=(self.config.kommo_responsible_user_id if role == "manager" else None),
            original_query=query_text,
            original_user_query=query_text,
            bot=bot,
            manager_ids=list(self.config.manager_ids),
        )

        rag_result_store: dict[str, Any] = {}

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "menu", "agent"],
        ):
            langfuse_handler = create_callback_handler()
            callbacks = [langfuse_handler] if langfuse_handler else []
            async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
                result = await self._ainvoke_supervisor_with_recovery(
                    agent=agent,
                    tools=tools,
                    role=role,
                    user_text=query_text,
                    chat_id=chat_id,
                    callbacks=callbacks,
                    bot_context=ctx,
                    rag_result_store=rag_result_store,
                )

        messages = result.get("messages", [])
        response_text = ""
        if messages:
            last_msg = messages[-1]
            response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        if response_text and not ctx.response_sent:
            for chunk in _split_telegram_response(response_text):
                try:
                    await callback.message.answer(chunk, parse_mode="Markdown")
                except Exception:
                    logger.warning("Markdown parse failed in menu action, falling back")
                    try:
                        await callback.message.answer(chunk)
                    except Exception:
                        logger.exception("Failed to send menu action response chunk")

    async def start(self):
        """Start bot polling."""
        logger.info("Starting bot...")

        # Initialize cache at startup
        if not self._cache_initialized:
            logger.info("Initializing cache service...")
            await self._cache.initialize()
            self._cache_initialized = True
            logger.info("Cache service ready")

        # Initialize conversation memory checkpointer (SDK)
        from .integrations.memory import create_fallback_checkpointer, create_redis_checkpointer

        try:
            self._checkpointer = create_redis_checkpointer(
                self.config.redis_url,
                ttl_minutes=7 * 24 * 60,  # 7 days; SDK uses minutes
                refresh_on_read=True,  # idle-based retention
            )
            await self._checkpointer.asetup()
            logger.info("Conversation memory checkpointer ready (Redis)")
        except Exception:
            logger.warning("Redis checkpointer init failed, using in-memory", exc_info=True)
            self._checkpointer = create_fallback_checkpointer()

        # Agent/voice checkpointer — Redis with TTL for bounded retention (#424).
        try:
            self._agent_checkpointer = create_redis_checkpointer(
                self.config.redis_url,
                ttl_minutes=self.config.agent_checkpointer_ttl_minutes,
                refresh_on_read=True,
            )
            await self._agent_checkpointer.asetup()
            logger.info(
                "Agent checkpointer ready (Redis, ttl=%s min)",
                self.config.agent_checkpointer_ttl_minutes,
            )
        except Exception:
            logger.warning("Agent Redis checkpointer init failed, using in-memory", exc_info=True)
            self._agent_checkpointer = create_fallback_checkpointer()

        # Initialize history service (Qdrant-backed Q&A history)
        try:
            self._history_service = HistoryService(
                client=self._qdrant.client,
                embeddings=self._embeddings,
                collection_name=self.config.qdrant_history_collection,
            )
            await self._history_service.ensure_collection()
            logger.info("History service ready (%s)", self.config.qdrant_history_collection)
        except Exception:
            logger.warning("History service init failed, /history disabled", exc_info=True)
            self._history_service = None

        # Initialize Kommo CRM client if enabled (#420: fail-safe, must not block startup)
        if self.config.kommo_enabled and self.config.kommo_subdomain:
            try:
                from .services.kommo_client import KommoClient
                from .services.kommo_tokens import KommoTokenStore

                if self._cache.redis is None:
                    logger.warning("Kommo CRM skipped: Redis client not initialized")
                    self._kommo_client = None
                else:
                    token_store = KommoTokenStore(
                        redis=self._cache.redis,
                        client_id=self.config.kommo_client_id,
                        client_secret=self.config.kommo_client_secret.get_secret_value(),
                        subdomain=self.config.kommo_subdomain,
                        redirect_uri=self.config.kommo_redirect_uri,
                    )
                    auth_code = self.config.kommo_auth_code or None
                    await token_store.initialize(authorization_code=auth_code)

                    self._kommo_client = KommoClient(
                        subdomain=self.config.kommo_subdomain,
                        token_store=token_store,
                    )
                    logger.info(
                        "Kommo CRM client initialized (subdomain=%s)",
                        self.config.kommo_subdomain,
                    )
            except Exception:
                logger.warning("Kommo CRM init failed — CRM features disabled", exc_info=True)
                self._kommo_client = None

        # Initialize PostgreSQL pool for realestate DB
        try:
            import asyncpg

            self._pg_pool = await asyncpg.create_pool(
                self.config.realestate_database_url,
                min_size=0,
                max_size=5,
                timeout=5,
            )
            logger.info("PostgreSQL pool ready (realestate)")

            from .services.user_service import UserService

            self._user_service = UserService(pool=self._pg_pool)

            # Initialize lead scoring store (#384)
            from .services.lead_scoring_store import LeadScoringStore

            self._lead_scoring_store = LeadScoringStore(pool=self._pg_pool)
            logger.info("Lead scoring store ready")

            # Initialize hot lead notifier (#402)
            if self.config.manager_ids and self._cache.redis is not None:
                try:
                    from .services.hot_lead_notifier import HotLeadNotifier

                    self._hot_lead_notifier = HotLeadNotifier(
                        bot=self.bot,
                        cache=self._cache,
                        manager_ids=self.config.manager_ids,
                        dedupe_ttl_sec=self.config.manager_hot_lead_dedupe_sec,
                    )
                    logger.info("Hot lead notifier ready (managers=%s)", self.config.manager_ids)
                except Exception:
                    logger.exception("Failed to initialize hot lead notifier")

            # Initialize nurturing scheduler (#390)
            if self.config.nurturing_enabled:
                try:
                    from .services.funnel_analytics_service import FunnelAnalyticsService
                    from .services.nurturing_scheduler import NurturingScheduler
                    from .services.nurturing_service import NurturingService

                    nurturing_svc = NurturingService(
                        pool=self._pg_pool,
                        bot=self.bot if self.config.nurturing_dispatch_enabled else None,
                        qdrant=self._qdrant if self.config.nurturing_dispatch_enabled else None,
                        llm=self._llm if self.config.nurturing_dispatch_enabled else None,
                    )
                    analytics_svc = FunnelAnalyticsService(pool=self._pg_pool)
                    self._nurturing_service = nurturing_svc
                    self._funnel_analytics_service = analytics_svc
                    self._nurturing_scheduler = NurturingScheduler(
                        nurturing_service=nurturing_svc,
                        analytics_service=analytics_svc,
                        lease_store=None,
                        config=self.config,
                    )
                    await self._nurturing_scheduler.start()
                    logger.info("Nurturing scheduler started")
                except Exception:
                    logger.exception("Failed to start nurturing scheduler")
        except Exception:
            logger.warning("PostgreSQL pool init failed, user features disabled", exc_info=True)

        # Initialize session summary worker (#445)
        self._session_summary_worker: Any | None = None
        if self.config.session_summary_enabled and self._cache.redis is not None:
            try:
                from .services.session_summary_worker import SessionSummaryWorker

                self._session_summary_worker = SessionSummaryWorker(
                    redis=self._cache.redis,
                    llm=self._llm,
                    kommo_client=self._kommo_client,
                    idle_timeout_min=self.config.session_idle_timeout_min,
                    poll_interval_sec=self.config.session_summary_poll_sec,
                    summary_model=self.config.session_summary_model,
                )
                await self._session_summary_worker.start()
                logger.info("SessionSummaryWorker started")
            except Exception:
                logger.exception("Failed to start SessionSummaryWorker")

        # Initialize i18n (fluentogram)
        from .middlewares.i18n import create_translator_hub, setup_i18n_middleware

        self._i18n_hub = create_translator_hub()
        setup_i18n_middleware(
            self.dp,
            self._i18n_hub,
            self._user_service,
            lead_scoring_store=self._lead_scoring_store,
            hot_lead_notifier=self._hot_lead_notifier,
            kommo_client=self._kommo_client,
            pg_pool=self._pg_pool,
            bot_config=self.config,
            property_bot=self,
        )
        logger.info("i18n middleware ready")

        # Setup aiogram-dialog
        from aiogram_dialog import setup_dialogs as aiogram_setup_dialogs

        from .dialogs.client_menu import client_menu_dialog
        from .dialogs.crm_submenu import crm_submenu_dialog
        from .dialogs.faq import faq_dialog
        from .dialogs.funnel import funnel_dialog
        from .dialogs.manager_menu import manager_menu_dialog
        from .dialogs.settings import settings_dialog

        self.dp.include_router(client_menu_dialog)
        self.dp.include_router(manager_menu_dialog)
        self.dp.include_router(crm_submenu_dialog)
        self.dp.include_router(settings_dialog)
        self.dp.include_router(funnel_dialog)
        self.dp.include_router(faq_dialog)
        aiogram_setup_dialogs(self.dp)
        logger.info("aiogram-dialog setup complete")

        # Preflight dependency checks
        from .preflight import check_dependencies

        await check_dependencies(self.config)

        # Start Redis health monitor (background task, every 5 min)
        await self._redis_monitor.start()

        # Register bot commands in Telegram menu
        await self.bot.set_my_commands(
            [
                BotCommand(command="start", description="Начать работу с ботом"),
                BotCommand(command="help", description="Помощь и примеры запросов"),
                BotCommand(command="clear", description="Очистить историю диалога"),
                BotCommand(command="history", description="Поиск по истории диалогов"),
                BotCommand(command="stats", description="Статистика кеша"),
                BotCommand(command="metrics", description="Метрики пайплайна (p50/p95)"),
                BotCommand(command="clearcache", description="Очистить кеш Redis"),
            ]
        )

        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")
        await self._redis_monitor.stop()
        await self._cache.close()
        await self._qdrant.close()
        if hasattr(self._embeddings, "aclose"):
            await self._embeddings.aclose()
        if hasattr(self._sparse, "aclose"):
            await self._sparse.aclose()
        if self._reranker and hasattr(self._reranker, "close"):
            await self._reranker.close()
        if self._kommo_client is not None:
            await self._kommo_client.close()
            self._kommo_client = None
        if self._llm_guard_client is not None and hasattr(self._llm_guard_client, "aclose"):
            await self._llm_guard_client.aclose()
        if self._checkpointer is not None:
            try:
                if hasattr(self._checkpointer, "__aexit__"):
                    await self._checkpointer.__aexit__(None, None, None)
            except Exception:
                logger.warning("Failed to close checkpointer cleanly", exc_info=True)
            finally:
                self._checkpointer = None
        if self._agent_checkpointer is not None:
            try:
                if hasattr(self._agent_checkpointer, "__aexit__"):
                    await self._agent_checkpointer.__aexit__(None, None, None)
            except Exception:
                logger.warning("Failed to close agent checkpointer cleanly", exc_info=True)
            finally:
                self._agent_checkpointer = None
        if getattr(self, "_session_summary_worker", None) is not None:
            await self._session_summary_worker.stop()
            self._session_summary_worker = None
        if self._nurturing_scheduler is not None:
            await self._nurturing_scheduler.stop()
            self._nurturing_scheduler = None
        self._nurturing_service = None
        self._funnel_analytics_service = None
        if self._pg_pool is not None:
            await self._pg_pool.close()
            logger.info("PostgreSQL pool closed")
        await self.bot.session.close()
