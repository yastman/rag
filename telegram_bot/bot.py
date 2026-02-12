"""Main Telegram bot logic — LangGraph pipeline."""

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

# --- Checkpoint namespace constants (versioned for safe migration) ---
_CHECKPOINT_NS_TEXT = "tg:text:v1"
_CHECKPOINT_NS_VOICE = "tg:voice:v1"

# --- Query type mapping for scores ---
_QUERY_TYPE_SCORE = {
    "CHITCHAT": 0.0,
    "OFF_TOPIC": 0.0,
    "SIMPLE": 1.0,
    "GENERAL": 1.0,
    "FAQ": 1.0,
    "ENTITY": 1.0,
    "STRUCTURED": 2.0,
    "COMPLEX": 2.0,
}


def _compute_checkpointer_overhead_proxy_ms(
    result: dict[str, Any], ainvoke_wall_ms: float
) -> float:
    """Compute proxy for checkpointer overhead: ainvoke wall-time minus sum of stage latencies.

    Returns max(0, delta) to clamp negative values from timing jitter.
    """
    stages_ms = sum(float(v) * 1000 for v in result.get("latency_stages", {}).values())
    return max(0.0, ainvoke_wall_ms - stages_ms)


def _write_langfuse_scores(lf: Any, result: dict) -> None:
    """Write Langfuse scores (14 + latency breakdown + 4 response length) from graph result state.

    Args:
        lf: Langfuse client (from get_client(), may be _NullLangfuseClient).
        result: State dict returned by graph.ainvoke().
    """
    latency_stages = result.get("latency_stages", {})
    total_ms = result.get("pipeline_wall_ms", 0.0)

    scores = {
        "query_type": _QUERY_TYPE_SCORE.get(result.get("query_type", ""), 1.0),
        "latency_total_ms": result.get("user_perceived_wall_ms", total_ms),
        "semantic_cache_hit": 1.0 if result.get("cache_hit") else 0.0,
        "embeddings_cache_hit": 1.0 if result.get("embeddings_cache_hit") else 0.0,
        "search_cache_hit": 1.0 if result.get("search_cache_hit") else 0.0,
        "rerank_applied": 1.0 if result.get("rerank_applied") else 0.0,
        "rerank_cache_hit": 0.0,  # Tracked when rerank cache implemented
        "results_count": float(result.get("search_results_count", 0)),
        "no_results": 1.0 if result.get("search_results_count", 0) == 0 else 0.0,
        "llm_used": 1.0 if "generate" in latency_stages else 0.0,
        "confidence_score": float(result.get("grade_confidence", 0.0)),
        "hyde_used": 0.0,  # HyDE not implemented in current pipeline
        "llm_ttft_ms": float(result.get("llm_ttft_ms", 0.0)),
        "llm_response_duration_ms": float(result.get("llm_response_duration_ms", 0.0)),
    }

    for name, value in scores.items():
        lf.score_current_trace(name=name, value=value)

    # --- Latency breakdown (#147) ---
    # Always-written BOOLEAN flags
    lf.score_current_trace(
        name="streaming_enabled",
        value=1 if result.get("streaming_enabled") else 0,
        data_type="BOOLEAN",
    )
    lf.score_current_trace(
        name="llm_timeout",
        value=1 if result.get("llm_timeout") else 0,
        data_type="BOOLEAN",
    )
    lf.score_current_trace(
        name="llm_stream_recovery",
        value=1 if result.get("llm_stream_recovery") else 0,
        data_type="BOOLEAN",
    )

    # Conditional NUMERIC + paired unavailable BOOLEAN flags
    decode_ms = result.get("llm_decode_ms")
    if decode_ms is not None:
        lf.score_current_trace(name="llm_decode_ms", value=float(decode_ms))
    else:
        lf.score_current_trace(name="llm_decode_unavailable", value=1, data_type="BOOLEAN")

    tps = result.get("llm_tps")
    if tps is not None:
        lf.score_current_trace(name="llm_tps", value=float(tps))
    else:
        lf.score_current_trace(name="llm_tps_unavailable", value=1, data_type="BOOLEAN")

    queue_ms = result.get("llm_queue_ms")
    if queue_ms is not None:
        lf.score_current_trace(name="llm_queue_ms", value=float(queue_ms))
    else:
        lf.score_current_trace(name="llm_queue_unavailable", value=1, data_type="BOOLEAN")

    # --- Response length control (#129) ---
    if "answer_words" in result:
        lf.score_current_trace(name="answer_words", value=float(result["answer_words"]))
    if "answer_chars" in result:
        lf.score_current_trace(name="answer_chars", value=float(result["answer_chars"]))
    if "answer_to_question_ratio" in result:
        lf.score_current_trace(
            name="answer_to_question_ratio",
            value=float(result["answer_to_question_ratio"]),
        )
    policy_mode = str(result.get("response_policy_mode", "disabled"))
    response_style = str(result.get("response_style", "")).strip()
    if response_style and policy_mode == "enforced":
        style_map = {"short": 0, "balanced": 1, "detailed": 2}
        lf.score_current_trace(
            name="response_style_applied",
            value=float(style_map.get(response_style, 1)),
        )

    # --- Voice transcription scores (#151) ---
    input_type = result.get("input_type", "text")
    lf.score_current_trace(name="input_type", value=input_type, data_type="CATEGORICAL")

    stt_ms = result.get("stt_duration_ms")
    if stt_ms is not None:
        lf.score_current_trace(name="stt_duration_ms", value=float(stt_ms))

    voice_dur = result.get("voice_duration_s")
    if voice_dur is not None:
        lf.score_current_trace(name="voice_duration_s", value=float(voice_dur))

    # --- Conversation memory (#154, #159) ---
    summarize_ms = result.get("latency_stages", {}).get("summarize", 0) * 1000
    if summarize_ms > 0:
        lf.score_current_trace(name="summarize_ms", value=summarize_ms)

    # Memory scores (#159)
    messages = result.get("messages", [])
    lf.score_current_trace(name="memory_messages_count", value=float(len(messages)))
    lf.score_current_trace(
        name="summarization_triggered",
        value=1 if summarize_ms > 0 else 0,
        data_type="BOOLEAN",
    )

    # Checkpointer overhead proxy (#159)
    if "checkpointer_overhead_proxy_ms" in result:
        lf.score_current_trace(
            name="checkpointer_overhead_proxy_ms",
            value=float(result["checkpointer_overhead_proxy_ms"]),
        )


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
    }


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
        )
        # Use hybrid as primary embeddings provider
        self._embeddings = self._hybrid
        self._sparse = BGEM3SparseEmbeddings(
            base_url=config.bge_m3_url,
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
        self.dp.message(F.voice)(self.handle_voice)
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

    @observe(name="telegram-rag-query")
    async def handle_query(self, message: Message):
        """Handle user query via LangGraph RAG pipeline."""
        pipeline_start = time.perf_counter()
        # Early typing ACK — user sees "typing..." immediately
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        state = make_initial_state(
            user_id=message.from_user.id,
            session_id=make_session_id("chat", message.chat.id),
            query=message.text or "",
        )
        state["max_rewrite_attempts"] = self._graph_config.max_rewrite_attempts

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
                checkpointer=self._checkpointer,
            )

            invoke_config = {
                "configurable": {
                    "thread_id": str(message.from_user.id),
                    "checkpoint_ns": _CHECKPOINT_NS_TEXT,
                }
            }
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                invoke_start = time.perf_counter()
                result = await graph.ainvoke(state, config=invoke_config)
                ainvoke_wall_ms = (time.perf_counter() - invoke_start) * 1000
                result["checkpointer_overhead_proxy_ms"] = _compute_checkpointer_overhead_proxy_ms(
                    result, ainvoke_wall_ms
                )

            # Wall-time for accurate latency_total_ms
            result["pipeline_wall_ms"] = (time.perf_counter() - pipeline_start) * 1000
            # User-perceived latency excludes post-respond summarization
            summarize_s = result.get("latency_stages", {}).get("summarize", 0)
            result["user_perceived_wall_ms"] = result["pipeline_wall_ms"] - (summarize_s * 1000)

            # Update trace with input/output and metadata
            lf = get_client()
            lf.update_current_trace(
                input={"query": message.text},
                output={"response": result.get("response", "")},
                metadata=_build_trace_metadata(result),
            )

            # Write Langfuse scores (14 + latency + response length #129)
            _write_langfuse_scores(lf, result)

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

        with propagate_attributes(
            session_id=state["session_id"],
            user_id=str(state["user_id"]),
            tags=["telegram", "rag", "voice"],
        ):
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
            )

            invoke_config = {
                "configurable": {
                    "thread_id": str(message.from_user.id),
                    "checkpoint_ns": _CHECKPOINT_NS_VOICE,
                }
            }
            try:
                async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                    invoke_start = time.perf_counter()
                    result = await graph.ainvoke(state, config=invoke_config)
                    ainvoke_wall_ms = (time.perf_counter() - invoke_start) * 1000
                    result["checkpointer_overhead_proxy_ms"] = (
                        _compute_checkpointer_overhead_proxy_ms(result, ainvoke_wall_ms)
                    )
            except ValueError as e:
                if "Empty transcription" in str(e):
                    await message.answer("Голосовое сообщение не содержит речи.")
                    return
                raise
            except Exception:
                logger.exception("Voice pipeline failed")
                await message.answer(
                    "Не удалось распознать голосовое сообщение. Попробуйте отправить текстом."
                )
                return

            result["pipeline_wall_ms"] = (time.perf_counter() - pipeline_start) * 1000
            # User-perceived latency excludes post-respond summarization
            summarize_s = result.get("latency_stages", {}).get("summarize", 0)
            result["user_perceived_wall_ms"] = result["pipeline_wall_ms"] - (summarize_s * 1000)

            lf = get_client()
            lf.update_current_trace(
                input={
                    "voice_duration_s": voice.duration,
                    "stt_text": result.get("stt_text", ""),
                },
                output={"response": result.get("response", "")},
                metadata=_build_trace_metadata(result),
            )

            _write_langfuse_scores(lf, result)

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
