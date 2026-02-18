"""Main Telegram bot logic — LangGraph pipeline."""

import asyncio
import hashlib
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
from aiogram.types import BotCommand, CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from .agents.supervisor import build_supervisor_graph
from .config import BotConfig
from .graph.config import GraphConfig
from .graph.graph import build_graph
from .graph.state import make_initial_state
from .middlewares import setup_error_middleware, setup_throttling_middleware
from .observability import get_client, get_langfuse_client, observe, propagate_attributes
from .scoring import (
    compute_checkpointer_overhead_proxy_ms,
    write_langfuse_scores,
)
from .services.history_service import HistoryService
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
    voice_duration_s: float | None = None,
    error_reason: str = "pipeline_error",
) -> None:
    """Write minimal Langfuse scores for voice traces that exit early (error paths).

    Ensures all voice traces have at least input_type and error context for dashboards.
    """
    lf.score_current_trace(name="input_type", value="voice", data_type="CATEGORICAL")
    lf.score_current_trace(name="voice_error_reason", value=error_reason, data_type="CATEGORICAL")
    if voice_duration_s is not None:
        lf.score_current_trace(name="voice_duration_s", value=float(voice_duration_s))


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

        # Redis health monitor (periodic background task)
        self._redis_monitor = RedisHealthMonitor(redis_url=config.redis_url)

        # Conversation memory checkpointer (initialized in start())
        self._checkpointer: Any = None

        # History service (initialized in start())
        self._history_service: HistoryService | None = None

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
        self.dp.message(F.voice)(self.handle_voice)
        self.dp.message(F.text)(self.handle_query)
        self.dp.callback_query(F.data.startswith("fb:"))(self.handle_feedback)

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
        assert message.from_user is not None
        user_id = message.from_user.id
        checkpointer_cleared = True

        if self._checkpointer is not None:
            try:
                await self._checkpointer.adelete_thread(str(user_id))
            except Exception:
                logger.warning("Failed to clear checkpointer thread %s", user_id, exc_info=True)
                checkpointer_cleared = False

        await self._cache.clear_conversation(user_id)
        if checkpointer_cleared:
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

            if self._history_service is None:
                lf.update_current_trace(
                    input={"command": "/history", "query": query},
                    output={"error": "service_unavailable"},
                    metadata={"user_id": user_id},
                )
                lf.score_current_trace(name="history_search_count", value=0, data_type="NUMERIC")
                lf.score_current_trace(name="history_search_empty", value=1.0, data_type="NUMERIC")
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
                lf.score_current_trace(name="history_search_count", value=0, data_type="NUMERIC")
                lf.score_current_trace(name="history_search_empty", value=1.0, data_type="NUMERIC")
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
            lf.score_current_trace(
                name="history_search_count", value=len(valid), data_type="NUMERIC"
            )
            lf.score_current_trace(
                name="history_search_latency_ms", value=search_ms, data_type="NUMERIC"
            )
            lf.score_current_trace(
                name="history_search_empty",
                value=1.0 if not valid else 0.0,
                data_type="NUMERIC",
            )
            lf.score_current_trace(name="history_backend", value="qdrant", data_type="CATEGORICAL")

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
    async def handle_query(self, message: Message):
        """Handle user query via supervisor graph (#310: supervisor-only)."""
        pipeline_start = time.perf_counter()
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        await self._handle_query_supervisor(message, pipeline_start)

    @observe(name="telegram-rag-supervisor")
    async def _handle_query_supervisor(self, message: Message, pipeline_start: float) -> None:
        """Handle query via supervisor graph (#240, #310 — primary query path)."""
        from .agents.rag_agent import create_rag_agent
        from .agents.tools import create_history_search_tool, direct_response
        from .graph.supervisor_state import make_supervisor_state

        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        user_id = message.from_user.id
        session_id = make_session_id("chat", message.chat.id)

        # Build supervisor tools
        tools = [
            create_rag_agent(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
            ),
            direct_response,
        ]
        if self._history_service is not None:
            tools.append(create_history_search_tool(history_service=self._history_service))

        # Build supervisor LLM (cheap model for routing)
        supervisor_llm = self._graph_config.create_llm(model_override=self.config.supervisor_model)

        supervisor_graph = build_supervisor_graph(
            supervisor_llm=supervisor_llm,
            tools=tools,
        )

        state = make_supervisor_state(
            user_id=user_id,
            session_id=session_id,
            query=message.text or "",
        )
        config = {
            "configurable": {
                "user_id": user_id,
                "session_id": session_id,
                # Judge sampling config passed to rag_search tool (#310)
                "judge_sample_rate": self.config.judge_sample_rate,
                "judge_model": self.config.judge_model,
                "llm_base_url": self.config.llm_base_url,
            }
        }

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "rag", "supervisor"],
        ):
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                result = await supervisor_graph.ainvoke(state, config=config)

            # Extract response from final message
            messages = result.get("messages", [])
            response_text = ""
            if messages:
                last_msg = messages[-1]
                response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            # Send response to user
            if response_text and not result.get("response_sent"):
                await message.answer(response_text)

            # Wall-time for the full supervisor pipeline
            wall_ms = (time.perf_counter() - pipeline_start) * 1000

            # Write Langfuse trace metadata
            lf = get_client()
            lf.update_current_trace(
                input={"query": message.text},
                output={"response": response_text},
                metadata={
                    "agent_used": result.get("agent_used", ""),
                    "supervisor_latency": result.get("latency_stages", {}).get("supervisor", 0),
                    "pipeline_mode": "supervisor",
                    "pipeline_wall_ms": wall_ms,
                },
            )
            # Supervisor-specific scores
            lf.score_current_trace(
                name="agent_used", value=result.get("agent_used", ""), data_type="CATEGORICAL"
            )
            supervisor_ms = result.get("latency_stages", {}).get("supervisor", 0) * 1000
            lf.score_current_trace(name="supervisor_latency_ms", value=supervisor_ms)
            lf.score_current_trace(
                name="supervisor_model", value=self.config.supervisor_model, data_type="CATEGORICAL"
            )

            # Persist Q&A to history (#310 — ported from monolith path)
            if self._history_service and response_text:
                try:
                    saved = await self._history_service.save_turn(
                        user_id=user_id,
                        session_id=session_id,
                        query=message.text or "",
                        response=response_text,
                        input_type="text",
                    )
                    lf.score_current_trace(
                        name="history_save_success",
                        value=1 if saved else 0,
                        data_type="BOOLEAN",
                    )
                    lf.score_current_trace(
                        name="history_backend", value="qdrant", data_type="CATEGORICAL"
                    )
                except Exception:
                    logger.warning("Failed to save history turn", exc_info=True)

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
                checkpointer=self._checkpointer,
                show_transcription=self.config.show_transcription,
                voice_language=self.config.voice_language,
                stt_model=self.config.stt_model,
                content_filter_enabled=self.config.content_filter_enabled,
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
                write_langfuse_scores(lf, result)
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
                    lf.score_current_trace(
                        name="history_save_success",
                        value=1 if saved else 0,
                        data_type="BOOLEAN",
                    )
                    lf.score_current_trace(
                        name="history_backend", value="qdrant", data_type="CATEGORICAL"
                    )
                except Exception:
                    logger.warning("Failed to save voice history turn", exc_info=True)

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
        if self._checkpointer is not None:
            try:
                if hasattr(self._checkpointer, "__aexit__"):
                    await self._checkpointer.__aexit__(None, None, None)
            except Exception:
                logger.warning("Failed to close checkpointer cleanly", exc_info=True)
            finally:
                self._checkpointer = None
        await self.bot.session.close()
