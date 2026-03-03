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
from urllib.parse import unquote, urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
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
from .handlers.handoff import (
    HandoffStates,
    create_handoff_router,
    get_user_qualification,
    parse_qual_callback,
    start_qualification,
)
from .keyboards.client_keyboard import build_client_keyboard, parse_menu_button
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
from .services.business_hours import is_business_hours
from .services.forum_bridge import ForumBridge
from .services.handoff_state import HandoffData, HandoffState
from .services.handoff_summary import generate_handoff_summary
from .services.history_service import HistoryService
from .services.metrics import PipelineMetrics
from .services.redis_monitor import RedisHealthMonitor


logger = logging.getLogger(__name__)

# --- Checkpoint namespace constants (versioned for safe migration) ---
_CHECKPOINT_NS_VOICE = "tg:voice:v1"
_FEEDBACK_CONFIRMATION_TTL_S = 5.0
_APARTMENT_PAGE_SIZE = 5


def _merge_results(existing: list[dict], extra: list[dict]) -> list[dict]:
    """Merge extra results into existing, deduplicating by id."""
    seen_ids: set[str] = set()
    for item in existing:
        if isinstance(item, dict) and item.get("id") is not None:
            seen_ids.add(str(item["id"]))
    merged = list(existing)
    for item in extra:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        item_key = str(item_id) if item_id is not None else ""
        if item_key and item_key in seen_ids:
            continue
        if item_key:
            seen_ids.add(item_key)
        merged.append(item)
    return merged


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
        "pipeline_wall_ms": result.get("pipeline_wall_ms"),
        "pre_agent_ms": result.get("pre_agent_ms"),
        "e2e_latency_ms": result.get("e2e_latency_ms"),
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


async def _seed_kommo_access_token(
    *,
    redis: Any,
    access_token: str,
    subdomain: str,
) -> bool:
    """Seed Redis with access_token from env when no auth_code and Redis empty.

    Returns True if seeded, False if skipped.
    """
    from .services.kommo_tokens import REDIS_KEY

    if not access_token:
        return False
    existing = await redis.hgetall(REDIS_KEY)
    if existing:
        return False
    await redis.hset(
        REDIS_KEY,
        mapping={
            "access_token": access_token,
            "refresh_token": "",
            "expires_at": "0",
            "subdomain": subdomain,
        },
    )
    logger.info("Kommo: seeded Redis from KOMMO_ACCESS_TOKEN (no refresh_token)")
    return True


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

        # Apartments collection (#629)
        from .services.apartments_service import ApartmentsService

        self._qdrant_apartments = QdrantService(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection_name="apartments",
        )
        self._apartments_service = ApartmentsService(qdrant=self._qdrant_apartments)

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

        # i18n hub (fluentogram) — initialize early for localized menu filters.
        self._i18n_hub: Any = None
        try:
            from .middlewares.i18n import create_translator_hub

            self._i18n_hub = create_translator_hub()
        except Exception:
            logger.warning(
                "Failed to initialize i18n hub during startup preflight; "
                "falling back to RU-only menu filters",
                exc_info=True,
            )

        # User service (asyncpg) — initialized in start()
        self._user_service: Any = None

        # PostgreSQL pool — initialized in start()
        self._pg_pool: Any = None

        # Kommo CRM client (initialized in start() if enabled)
        self._kommo_client: Any | None = None

        # Lead scoring store (initialized in start() with pg_pool)
        self._lead_scoring_store: Any | None = None

        # Favorites service (initialized in start() with pg_pool)
        self._favorites_service: Any = None

        # Nurturing scheduler (initialized in start() if enabled)
        self._nurturing_scheduler: Any | None = None

        # Manager runtime services (initialized in start() if enabled)
        self._nurturing_service: Any | None = None
        self._funnel_analytics_service: Any | None = None

        # Hot lead notifier (initialized in start() when manager_ids configured)
        self._hot_lead_notifier: Any | None = None

        # Handoff services (Forum Topics bridge + Redis state machine)
        self._handoff_state: HandoffState | None = None
        self._forum_bridge: ForumBridge | None = None
        self._bot_user_id: int | None = None

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

    @staticmethod
    def _extract_database_name(database_url: str) -> str | None:
        """Extract database name from PostgreSQL URL."""
        parsed = urlparse(database_url)
        raw_path = (parsed.path or "").lstrip("/")
        if not raw_path:
            return None
        return unquote(raw_path.split("/", 1)[0]) or None

    async def _ensure_postgres_database_exists(
        self, asyncpg_module: Any, database_name: str
    ) -> bool:
        """Ensure target PostgreSQL database exists, creating it when missing."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database_name):
            logger.error("Unsafe PostgreSQL database name: %r", database_name)
            return False

        admin_conn: Any = None
        try:
            # Connect to maintenance DB to run CREATE DATABASE (required by PostgreSQL).
            admin_conn = await asyncpg_module.connect(
                self.config.realestate_database_url,
                timeout=5,
                database="postgres",
            )
            exists = await admin_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                database_name,
            )
            if exists:
                return True

            escaped_name = database_name.replace('"', '""')
            await admin_conn.execute(f'CREATE DATABASE "{escaped_name}"')
            logger.info("Created PostgreSQL database: %s", database_name)
            return True
        except Exception as exc:
            duplicate_error = getattr(asyncpg_module, "DuplicateDatabaseError", None)
            if duplicate_error is not None and isinstance(exc, duplicate_error):
                logger.info(
                    "PostgreSQL database already exists after concurrent create: %s", database_name
                )
                return True
            logger.warning(
                "Failed to ensure PostgreSQL database exists: %s",
                database_name,
                exc_info=True,
            )
            return False
        finally:
            if admin_conn is not None:
                with contextlib.suppress(Exception):
                    await admin_conn.close()

    async def _ensure_realestate_schema(self) -> None:
        """Idempotent bootstrap for realestate runtime tables."""
        if self._pg_pool is None:
            return

        schema_statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                locale VARCHAR(5) DEFAULT 'ru',
                role VARCHAR(20) DEFAULT 'client',
                first_name VARCHAR(100),
                telegram_language_code VARCHAR(10),
                notifications_enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                stage VARCHAR(30) DEFAULT 'new',
                score INTEGER DEFAULT 0,
                preferences JSONB DEFAULT '{}',
                kommo_lead_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS funnel_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                event_type VARCHAR(50) NOT NULL,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS lead_scores (
                id BIGSERIAL PRIMARY KEY,
                lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                session_id TEXT NOT NULL,
                score_value INTEGER NOT NULL CHECK (score_value BETWEEN 0 AND 100),
                score_band TEXT NOT NULL CHECK (score_band IN ('hot', 'warm', 'cold')),
                reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
                kommo_lead_id BIGINT,
                sync_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (sync_status IN ('pending', 'synced', 'failed')),
                sync_attempts INTEGER NOT NULL DEFAULT 0,
                last_synced_at TIMESTAMPTZ,
                sync_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (lead_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS lead_score_sync_audit (
                id BIGSERIAL PRIMARY KEY,
                lead_score_id BIGINT NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
                idempotency_key TEXT NOT NULL,
                sync_status TEXT NOT NULL,
                http_status INTEGER,
                response_excerpt TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS nurturing_jobs (
                id BIGSERIAL PRIMARY KEY,
                lead_score_id BIGINT NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
                scheduled_for TIMESTAMPTZ NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'sent', 'failed', 'skipped')),
                channel TEXT NOT NULL DEFAULT 'telegram',
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (lead_score_id, scheduled_for)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS funnel_metrics_daily (
                id BIGSERIAL PRIMARY KEY,
                metric_date DATE NOT NULL,
                stage_name TEXT NOT NULL,
                entered_count INTEGER NOT NULL DEFAULT 0,
                converted_count INTEGER NOT NULL DEFAULT 0,
                dropoff_count INTEGER NOT NULL DEFAULT 0,
                conversion_rate NUMERIC(6,4) NOT NULL DEFAULT 0,
                prev_stage_count INTEGER NOT NULL DEFAULT 0,
                step_conversion_rate NUMERIC(6,4) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (metric_date, stage_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS scheduler_leases (
                lease_name TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                lease_until TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_favorites (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                property_id TEXT NOT NULL,
                property_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (telegram_id, property_id)
            )
            """,
            "ALTER TABLE funnel_events ADD COLUMN IF NOT EXISTS stage_name TEXT",
            "CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)",
            "CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage)",
            "CREATE INDEX IF NOT EXISTS idx_funnel_events_user_id ON funnel_events(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_funnel_events_created ON funnel_events(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_funnel_events_created_stage ON funnel_events (created_at DESC, stage_name)",
            "CREATE INDEX IF NOT EXISTS idx_lead_scores_pending_sync ON lead_scores (sync_status, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_lead_scores_band_sync ON lead_scores (score_band, sync_status, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_nurturing_jobs_pending ON nurturing_jobs (status, scheduled_for ASC)",
            "CREATE INDEX IF NOT EXISTS idx_user_favorites_telegram_id ON user_favorites (telegram_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_favorites_created_at ON user_favorites (created_at DESC)",
        ]
        for stmt in schema_statements:
            await self._pg_pool.execute(stmt)

    def _register_handlers(self):
        """Register message handlers."""
        # Phone collector FSM — include before catch-all handlers (#628)
        from .handlers.phone_collector import create_phone_router

        self.dp.include_router(create_phone_router())

        # Handoff qualification callbacks — qual:goal/budget (#730)
        self.dp.include_router(create_handoff_router())
        # Final qualification step — triggers handoff completion (#730 review)
        self.dp.callback_query(F.data.startswith("qual:contact:"))(self._on_qual_contact)

        # Group message handler — manager → client relay (#730)
        if self.config.managers_group_id:
            self.dp.message(
                F.chat.id == self.config.managers_group_id,
                F.message_thread_id,
            )(self._handle_group_message)

        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("help"))(self.cmd_help)
        self.dp.message(Command("clear"))(self.cmd_clear)
        self.dp.message(Command("stats"))(self.cmd_stats)
        self.dp.message(Command("metrics"))(self.cmd_metrics)
        self.dp.message(Command("call"))(self.cmd_call)
        self.dp.message(Command("history"))(self.cmd_history)
        self.dp.message(Command("clearcache"))(self.cmd_clearcache)
        self.dp.message(F.voice)(self.handle_voice)
        # ReplyKeyboard buttons — registered before catch-all F.text (#628)
        from .keyboards.client_keyboard import get_menu_button_texts

        menu_button_texts = tuple(get_menu_button_texts(self._i18n_hub))
        self.dp.message(F.text.in_(menu_button_texts), flags={"menu_nav": True})(
            self.handle_menu_button
        )
        self.dp.message(StateFilter(None), F.text)(self.handle_query)
        self.dp.callback_query(F.data.startswith("fb:"))(self.handle_feedback)
        self.dp.callback_query(F.data.startswith("hitl:"))(self.handle_hitl_callback)
        self.dp.callback_query(F.data.startswith("cc:"))(self.handle_clearcache_callback)
        # Client menu inline callbacks (#628)
        self.dp.callback_query(F.data.startswith("svc:"))(self.handle_service_callback)
        self.dp.callback_query(F.data.startswith("cta:"))(self.handle_cta_callback)
        self.dp.callback_query(F.data.startswith("fav:"))(self.handle_favorite_callback)
        self.dp.callback_query(F.data.startswith("results:"))(self.handle_results_callback)
        self.dp.callback_query(F.data.startswith("card:"))(self.handle_card_callback)

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

    async def cmd_start(self, message: Message, dialog_manager: Any = None, i18n: Any = None):
        """Handle /start command — ReplyKeyboard for clients, dialog for managers."""
        assert message.from_user is not None
        role = await self._resolve_user_role(message.from_user.id)

        kommo_enabled = getattr(self.config, "kommo_enabled", False)
        if role == "manager" and kommo_enabled and dialog_manager is not None:
            from aiogram_dialog import StartMode

            from .dialogs.states import ManagerMenuSG

            await dialog_manager.start(ManagerMenuSG.main, mode=StartMode.RESET_STACK)
        else:
            # Client: persistent ReplyKeyboard (#628)
            name = message.from_user.first_name or ""
            if i18n is not None:
                welcome = i18n.get("welcome-text", name=name)
            else:
                from .services.content_loader import load_services_config

                cfg = load_services_config()
                welcome = cfg.get("welcome", {}).get("text", "Добро пожаловать!")
            await message.answer(welcome, reply_markup=build_client_keyboard(i18n=i18n))

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
                    InlineKeyboardButton(text="Search+Rerank", callback_data="cc:search"),
                ],
                [InlineKeyboardButton(text="Все", callback_data="cc:all")],
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
        trace_id = ""
        try:
            trace_id = get_client().get_current_trace_id() or ""
        except Exception:
            logger.debug("Failed to resolve current Langfuse trace id for /call", exc_info=True)
        if not trace_id:
            trace_id = f"call-{uuid.uuid4().hex}"

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
                                "langfuse_trace_id": trace_id,
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

    async def handle_menu_button(
        self,
        message: Message,
        state: FSMContext,
        dialog_manager: Any = None,
        i18n: Any = None,
    ) -> None:
        """Route ReplyKeyboard button press to dedicated handler (#628, #658)."""
        action_id = parse_menu_button(
            message.text or "",
            i18n_hub=getattr(self, "_i18n_hub", None),
        )
        if action_id is None:
            return

        # Clear only phone-collection FSM state to avoid wiping unrelated flows (#658)
        current = await state.get_state()
        if isinstance(current, str) and current.startswith("PhoneCollectorStates:"):
            await state.clear()

        handlers: dict[str, Any] = {
            "search": self._handle_search,
            "services": self._handle_services,
            "viewing": self._handle_viewing,
            "bookmarks": self._handle_bookmarks,
            "promotions": self._handle_promotions,
            "manager": self._handle_manager,
        }
        handler = handlers.get(action_id)
        if handler:
            if action_id != "bookmarks":
                await state.update_data(bookmarks_context=False)
            if action_id == "search":
                await handler(message, dialog_manager)
            elif action_id == "bookmarks":
                await handler(message, state)
            elif action_id == "viewing":
                await handler(message, state, dialog_manager)
            elif action_id == "services":
                await handler(message, i18n=i18n)
            elif action_id == "manager":
                await handler(message, i18n=i18n, state=state)
            else:
                await handler(message)

    async def handle_menu_action_text(self, message: Message, query_text: str) -> None:
        """Dispatch text query to agent pipeline (from ReplyKeyboard context) (#628)."""
        patched = message.model_copy(update={"text": query_text})
        await self.handle_query(patched)

    async def _handle_search(self, message: Message, dialog_manager: Any = None) -> None:
        """Start property search funnel via aiogram-dialog (#628, #658)."""
        if dialog_manager is not None:
            from aiogram_dialog import StartMode

            from .dialogs.states import FunnelSG

            await dialog_manager.start(FunnelSG.city, mode=StartMode.RESET_STACK)
        else:
            # Fallback when dialog_manager not available (e.g., tests)
            await self.handle_menu_action_text(message, "Подбери апартаменты")

    async def _handle_services(self, message: Message, i18n: Any = None) -> None:
        """Show services inline menu (#628)."""
        from .keyboards.services_keyboard import build_services_menu

        if i18n is not None:
            text = i18n.get("services-menu-text")
        else:
            text = "Выберите услугу, чтобы узнать подробнее:"
        kb = build_services_menu(i18n=i18n)
        await message.answer(text, reply_markup=kb)

    async def _handle_viewing(
        self, message: Message, state: FSMContext, dialog_manager: Any = None
    ) -> None:
        """Start viewing appointment wizard via aiogram-dialog (#719)."""
        if dialog_manager is not None:
            from aiogram_dialog import StartMode

            from .dialogs.states import ViewingSG

            await dialog_manager.start(ViewingSG.objects, mode=StartMode.RESET_STACK)
        else:
            await message.answer("📅 Для записи на осмотр используйте кнопку меню.")

    async def _send_property_card(
        self,
        message: Message,
        result: dict,
        telegram_id: int,
    ) -> Message:
        """Send a single property card with preview photo and action buttons (#722)."""
        from .keyboards.property_card import (
            build_card_buttons,
            format_property_card,
            get_demo_photo_paths,
        )

        p = result.get("payload", {})
        card = format_property_card(
            property_id=result["id"],
            complex_name=p.get("complex_name", ""),
            location=p.get("city", ""),
            property_type=p.get("property_type", ""),
            floor=p.get("floor", 0),
            area_m2=p.get("area_m2", 0),
            view=", ".join(p.get("view_tags", [])) or p.get("view_primary", ""),
            price_eur=p.get("price_eur", 0),
        )
        favorites_service = getattr(self, "_favorites_service", None)
        is_fav = False
        if favorites_service is not None:
            is_fav = await favorites_service.is_favorited(telegram_id, result["id"])
        demo_photos = get_demo_photo_paths()
        reply_markup = build_card_buttons(
            result["id"],
            is_favorited=is_fav,
        )
        photo_message_ids: list[int] = []
        if demo_photos:
            try:
                media = [InputMediaPhoto(media=FSInputFile(path)) for path in demo_photos]
                sent_photos = await message.answer_media_group(media=media)
                photo_message_ids = [m.message_id for m in sent_photos]
            except Exception:
                logger.warning("Failed to send photo album, falling back to text", exc_info=True)

        card_msg = await message.answer(card, reply_markup=reply_markup)
        card_msg._photo_message_ids = photo_message_ids  # type: ignore[attr-defined]
        return card_msg

    async def _handle_bookmarks(self, message: Message, state: FSMContext | None = None) -> None:
        """Show user's saved favorites (#628)."""
        if not message.from_user:
            return

        favorites_service = getattr(self, "_favorites_service", None)
        if favorites_service is None:
            await message.answer("Закладки временно недоступны.")
            return

        items = await favorites_service.list(telegram_id=message.from_user.id)
        if not items:
            await message.answer(
                "📌 У вас пока нет закладок.\n\n"
                "Нажмите «🏠 Подбор апартаментов» чтобы найти квартиру."
            )
            return

        bookmark_message_ids: list[int] = []
        bookmark_photo_ids: dict[int, list[int]] = {}
        for fav in items:
            d = fav.property_data
            result_like = {
                "id": fav.property_id,
                "payload": {
                    "complex_name": d.get("complex_name", ""),
                    "city": d.get("location", ""),
                    "property_type": d.get("property_type", ""),
                    "floor": d.get("floor", 0),
                    "area_m2": d.get("area_m2", 0),
                    "view_tags": [],
                    "view_primary": d.get("view", ""),
                    "price_eur": d.get("price_eur", 0),
                },
            }
            sent = await self._send_property_card(message, result_like, message.from_user.id)
            msg_id = getattr(sent, "message_id", None)
            if isinstance(msg_id, int):
                bookmark_message_ids.append(msg_id)
                photo_ids = getattr(sent, "_photo_message_ids", [])
                if photo_ids:
                    bookmark_photo_ids[msg_id] = photo_ids

        if state is not None:
            await state.update_data(
                bookmarks_context=True,
                bookmark_message_ids=bookmark_message_ids,
                bookmark_photo_ids=bookmark_photo_ids,
            )

    async def _handle_promotions(self, message: Message) -> None:
        """Show promotions from config (#628)."""
        from .services.content_loader import get_promotions

        promos = get_promotions()
        if not promos:
            await message.answer("Актуальных акций пока нет.")
            return

        lines = []
        for p in promos:
            lines.append(f"{p['emoji']} {p['title']}\n{p['text']}")
        text = "\n\n".join(lines)
        await message.answer(text)

    async def _handle_manager(
        self, message: Message, i18n: Any = None, state: FSMContext | None = None
    ) -> None:
        """Handoff to manager (#628, #730)."""
        if self._forum_bridge is not None:
            await start_qualification(message, i18n=i18n, state=state)
        else:
            await self.handle_menu_action_text(message, "Соедини с менеджером")

    async def _handle_group_message(self, message: Message) -> None:
        """Handle messages in managers group — relay to client (#730)."""
        if not message.message_thread_id:
            return
        if message.from_user and self._bot_user_id and message.from_user.id == self._bot_user_id:
            return  # Skip own messages (echo).

        if self._handoff_state is None:
            return
        handoff = await self._handoff_state.get_by_topic(message.message_thread_id)
        if not handoff:
            return

        # /close command — return client to bot.
        if message.text and message.text.strip().lower() == "/close":
            await self._close_handoff(handoff)
            return

        # First manager message — transition human_waiting → human.
        if handoff.mode == "human_waiting":
            await self._handoff_state.update_mode(handoff.client_id, "human")
            manager_name = message.from_user.full_name if message.from_user else "Менеджер"
            await self.bot.send_message(
                chat_id=handoff.client_id,
                text=f"🟢 {manager_name} подключился к чату",
            )

        # Relay manager message to client.
        if self._forum_bridge is not None:
            try:
                await self._forum_bridge.relay_to_client(
                    topic_id=message.message_thread_id,
                    message_id=message.message_id,
                    client_chat_id=handoff.client_id,
                )
            except TelegramBadRequest:
                logger.warning("Failed to relay message to client %s", handoff.client_id)

    async def _on_qual_contact(self, callback: CallbackQuery, state: FSMContext) -> None:
        """Handle final qualification step — create topic + state (#730 review)."""
        await callback.answer()
        parsed = parse_qual_callback(callback.data or "")
        if not parsed:
            return
        _, value = parsed

        qualification = get_user_qualification(callback.from_user.id)
        qualification["contact"] = value

        user_id = callback.from_user.id
        msg = callback.message
        if value == "chat" and self._forum_bridge is not None:
            if msg and hasattr(msg, "edit_text"):
                await msg.edit_text("Соединяю с менеджером...")
            display_name = callback.from_user.full_name or "User"
            username = callback.from_user.username
            locale = "ru"
            await self._complete_handoff(
                user_id=user_id,
                username=username,
                display_name=display_name,
                locale=locale,
                qualification=qualification,
                message=msg,
                state=state,
            )
        elif value == "phone":
            if msg and hasattr(msg, "edit_text"):
                await msg.edit_text("Сейчас попросим номер телефона...")
        else:
            # Fallback — delegate to agent pipeline.
            if msg and hasattr(msg, "edit_text"):
                await msg.edit_text("Соединяю с менеджером...")

    async def _complete_handoff(
        self,
        user_id: int,
        username: str | None,
        display_name: str,
        locale: str,
        qualification: dict[str, str],
        message: Any,
        state: FSMContext | None = None,
    ) -> None:
        """Create forum topic + Kommo lead + set handoff state (#730)."""
        if self._forum_bridge is None:
            return

        # Stale topic cleanup: if Redis has data but topic is deleted — clean up.
        if self._handoff_state is not None:
            existing = await self._handoff_state.get_by_client(user_id)
            if existing is not None:
                topic_alive = await self._forum_bridge.send_to_topic(
                    topic_id=existing.topic_id,
                    text="⚡ Клиент повторно запросил связь с менеджером.",
                )
                if topic_alive:
                    # Topic still exists — FSM guard should have caught this, but just in case.
                    if state is not None:
                        await state.set_state(HandoffStates.active)
                    return
                logger.info("Stale handoff topic %s — recreating", existing.topic_id)
                await self._handoff_state.delete(user_id)

        goal_map = {"buy": "Покупка", "rent": "Аренда", "consult": "Консультация"}
        goal_text = goal_map.get(qualification.get("goal", ""), "Консультация")

        # 1. Create forum topic.
        try:
            topic_id = await self._forum_bridge.create_topic(
                client_name=display_name,
                goal=goal_text,
            )
        except TelegramBadRequest:
            logger.exception("Forum Topics unavailable — bot lacks can_manage_topics")
            if message and hasattr(message, "answer"):
                await message.answer("Менеджер скоро свяжется с вами!")
            return

        # 2. AI summary (if sufficient history).
        summary = None
        history: list[dict[str, str]] = []
        if self._cache.redis is not None:
            try:
                raw = await self._cache.redis.lrange(f"conversation:{user_id}", 0, -1)
                for item in raw:
                    entry = json.loads(item) if isinstance(item, str) else item
                    if isinstance(entry, dict) and "role" in entry and "content" in entry:
                        history.append({"role": entry["role"], "content": entry["content"]})
            except Exception:
                logger.warning("Failed to fetch chat history for handoff summary")
        if len(history) >= self.config.handoff_summary_min_messages:
            summary = await generate_handoff_summary(history, llm=self._llm)

        # 3. Kommo lead (optional).
        lead_url = None
        lead_id = None
        if self._kommo_client is not None:
            try:
                from .services.kommo_models import LeadCreate

                lead = await self._kommo_client.create_lead(
                    LeadCreate(name=f"Handoff: {display_name}")
                )
                lead_id = lead.id
                lead_url = f"https://{self.config.kommo_subdomain}.kommo.com/leads/detail/{lead.id}"
            except Exception:
                logger.exception("Kommo lead creation failed during handoff")

        # 4. Post context pack.
        await self._forum_bridge.post_context_pack(
            topic_id=topic_id,
            client_name=display_name,
            username=username,
            locale=locale,
            qualification=qualification,
            summary=summary,
            lead_url=lead_url,
        )

        # 5. Set Redis state + FSM.
        data = HandoffData(
            client_id=user_id,
            topic_id=topic_id,
            lead_id=lead_id,
            mode="human_waiting",
            qualification=qualification,
        )
        if self._handoff_state is not None:
            await self._handoff_state.set(data)
        if state is not None:
            await state.set_state(HandoffStates.active)

        # 6. Business hours notice.
        in_hours = is_business_hours(
            start=self.config.business_hours_start,
            end=self.config.business_hours_end,
            tz=self.config.business_hours_tz,
        )
        if not in_hours:
            start_h = self.config.business_hours_start
            end_h = self.config.business_hours_end
            await message.answer(
                "📨 Ваш запрос принят!\n\n"
                "Менеджер ответит в рабочее время:\n"
                f"Пн–Пт, {start_h}:00–{end_h}:00 (🇧🇬 София)\n\n"
                "Мы пришлём уведомление, когда менеджер подключится."
            )

    async def _close_handoff(self, handoff: HandoffData) -> None:
        """Manager sends /close — return client to bot (#730)."""
        # Notify topic.
        if self._forum_bridge is not None:
            await self._forum_bridge.send_to_topic(
                topic_id=handoff.topic_id,
                text="✅ Диалог закрыт, клиент возвращён боту.",
            )
            await self._forum_bridge.close_topic(topic_id=handoff.topic_id)

        # Notify client.
        await self.bot.send_message(
            chat_id=handoff.client_id,
            text="Диалог с менеджером завершён.\n\n🤖 Вы снова общаетесь с ботом. Задавайте вопросы — помогу!",
        )

        # Cleanup Redis + FSM state.
        if self._handoff_state is not None:
            await self._handoff_state.delete(handoff.client_id)
        # Clear client's FSM state from group context via storage key.
        from aiogram.fsm.storage.base import StorageKey

        key = StorageKey(bot_id=self.bot.id, chat_id=handoff.client_id, user_id=handoff.client_id)
        await self.dp.storage.set_state(key, state=None)

        # Update Kommo (optional).
        if self._kommo_client is not None and handoff.lead_id is not None:
            try:
                await self._kommo_client.add_note(
                    "leads", handoff.lead_id, "Диалог с клиентом завершён менеджером."
                )
            except Exception:
                logger.exception("Failed to update Kommo on handoff close")

    async def handle_service_callback(self, callback: CallbackQuery, i18n: Any = None) -> None:
        """Handle service menu inline button clicks (#628)."""
        from .keyboards.services_keyboard import (
            build_service_card_buttons,
            build_services_menu,
            parse_service_callback,
        )
        from .services.content_loader import get_service_card

        parsed = parse_service_callback(callback.data or "")
        if parsed is None:
            await callback.answer()
            return

        action, param = parsed

        if action == "back":
            if callback.message:
                await callback.message.delete()
            await callback.answer()

        elif action == "menu":
            if i18n is not None:
                text = i18n.get("services-menu-text")
            else:
                text = "Выберите услугу, чтобы узнать подробнее:"
            kb = build_services_menu(i18n=i18n)
            if callback.message:
                await callback.message.edit_text(text, reply_markup=kb)
            await callback.answer()

        elif action == "service" and param:
            svc = get_service_card(param)
            if svc:
                kb = build_service_card_buttons(param, i18n=i18n)
                ftl_key = f"svc-{param.replace('_', '-')}-card"
                card_text = (i18n.get(ftl_key) if i18n is not None else None) or svc.get(
                    "card_text", ""
                )
                if callback.message:
                    await callback.message.edit_text(card_text, reply_markup=kb)
            await callback.answer()

        else:
            await callback.answer()

    async def handle_cta_callback(self, callback: CallbackQuery, state: FSMContext) -> None:
        """Handle CTA button clicks (get_offer, manager) (#628)."""
        from .handlers.phone_collector import start_phone_collection
        from .keyboards.services_keyboard import parse_service_callback

        parsed = parse_service_callback(callback.data or "")
        if parsed is None:
            await callback.answer()
            return

        action, param = parsed

        if action == "get_offer":
            await start_phone_collection(callback, state, service_key=param or "unknown")
        elif action == "manager":
            if self._forum_bridge is not None:
                # Forum Topics enabled — same qualification flow as menu (#730).
                await start_qualification(callback, i18n=None, state=state)
            else:
                await start_phone_collection(callback, state, service_key="manager")
        else:
            await callback.answer()

    async def handle_favorite_callback(self, callback: CallbackQuery, state: FSMContext) -> None:
        """Handle favorite add/remove/viewing callbacks (#628)."""
        data = callback.data or ""
        parts = data.split(":", 2)

        if len(parts) < 2 or not callback.from_user:
            await callback.answer()
            return

        action = parts[1]
        property_id = parts[2] if len(parts) > 2 else ""

        favorites_service = getattr(self, "_favorites_service", None)
        if favorites_service is None:
            await callback.answer("Закладки недоступны")
            return

        if action == "add" and property_id:
            # Build property_data from saved apartment results (#655, #664)
            state_data = await state.get_data()
            raw_results = state_data.get("apartment_results")
            apt_results = raw_results if isinstance(raw_results, list) else []
            matched = next(
                (r for r in apt_results if isinstance(r, dict) and r.get("id") == property_id),
                None,
            )
            if matched:
                payload = matched.get("payload")
                if not isinstance(payload, dict):
                    property_data: dict[str, Any] = {}
                else:
                    p = payload
                    property_data = {
                        "complex_name": p.get("complex_name", ""),
                        "location": p.get("city", ""),
                        "property_type": p.get("property_type", ""),
                        "floor": p.get("floor", 0),
                        "area_m2": p.get("area_m2", 0),
                        "view": ", ".join(p.get("view_tags", [])) or p.get("view_primary", ""),
                        "price_eur": p.get("price_eur", 0),
                    }
            else:
                property_data = {}
            result = await favorites_service.add(
                telegram_id=callback.from_user.id,
                property_id=property_id,
                property_data=property_data,
            )
            if result:
                await callback.answer("Добавлено в закладки")
                if callback.message:
                    from .keyboards.property_card import build_card_buttons

                    with contextlib.suppress(Exception):
                        await callback.message.edit_reply_markup(
                            reply_markup=build_card_buttons(property_id, is_favorited=True)
                        )
            else:
                await callback.answer("Уже в закладках")

        elif action == "remove" and property_id:
            await favorites_service.remove(
                telegram_id=callback.from_user.id, property_id=property_id
            )
            state_data = await state.get_data()
            raw_results = state_data.get("apartment_results")
            apt_results = raw_results if isinstance(raw_results, list) else []
            in_search_results = any(
                isinstance(r, dict) and r.get("id") == property_id for r in apt_results
            )
            raw_bookmark_ids = state_data.get("bookmark_message_ids")
            bookmark_message_ids = (
                {mid for mid in raw_bookmark_ids if isinstance(mid, int)}
                if isinstance(raw_bookmark_ids, list)
                else set()
            )
            callback_message_id = getattr(callback.message, "message_id", None)
            is_bookmark_message = (
                isinstance(callback_message_id, int) and callback_message_id in bookmark_message_ids
            )
            if in_search_results and not is_bookmark_message and callback.message:
                from .keyboards.property_card import build_card_buttons

                with contextlib.suppress(Exception):
                    await callback.message.edit_reply_markup(
                        reply_markup=build_card_buttons(property_id, is_favorited=False)
                    )
                await callback.answer("Удалено из закладок")
            else:
                if callback.message:
                    # Delete photo album messages linked to this card
                    raw_photo_ids = state_data.get("bookmark_photo_ids", {})
                    photo_ids = (
                        raw_photo_ids.get(callback_message_id, [])
                        if isinstance(raw_photo_ids, dict) and isinstance(callback_message_id, int)
                        else []
                    )
                    chat_id = callback.message.chat.id
                    for pid in photo_ids:
                        with contextlib.suppress(Exception):
                            await callback.message.bot.delete_message(  # type: ignore[union-attr]
                                chat_id=chat_id,
                                message_id=pid,
                            )
                    await callback.message.delete()
                await callback.answer("Удалено из закладок")

        elif action == "viewing" and property_id:
            from .handlers.phone_collector import start_phone_collection

            # Загрузить данные объекта из favorites
            fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
            viewing_objs = []
            for fav in fav_items:
                if fav.property_id == property_id:
                    d = fav.property_data
                    viewing_objs.append(
                        {
                            "id": fav.property_id,
                            "complex_name": d.get("complex_name", ""),
                            "property_type": d.get("property_type", ""),
                            "area_m2": d.get("area_m2", 0),
                            "price_eur": d.get("price_eur", 0),
                        }
                    )
                    break
            await start_phone_collection(
                callback, state, service_key="viewing", viewing_objects=viewing_objs or None
            )

        elif action == "viewing_all":
            from .handlers.phone_collector import start_phone_collection

            fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
            viewing_objs = []
            for fav in fav_items:
                d = fav.property_data
                viewing_objs.append(
                    {
                        "id": fav.property_id,
                        "complex_name": d.get("complex_name", ""),
                        "property_type": d.get("property_type", ""),
                        "area_m2": d.get("area_m2", 0),
                        "price_eur": d.get("price_eur", 0),
                    }
                )
            await start_phone_collection(
                callback, state, service_key="viewing", viewing_objects=viewing_objs or None
            )

        else:
            await callback.answer()

    async def handle_results_callback(self, callback: CallbackQuery, state: FSMContext) -> None:
        """Handle property results callbacks (more/refine/viewing) (#654)."""
        from .keyboards.property_card import build_results_footer

        data = callback.data or ""
        if data == "results:more":
            state_data = await state.get_data()
            results = state_data.get("apartment_results")
            offset = state_data.get("apartment_offset", 0)
            if not results:
                await callback.answer("Нет сохранённых результатов")
                return
            apartment_total = state_data.get("apartment_total", len(results))
            apartment_total_value = (
                apartment_total if isinstance(apartment_total, int) else len(results)
            )
            apartment_next_offset = state_data.get("apartment_next_offset")
            apartment_filters = state_data.get("apartment_filters")
            new_offset = offset + _APARTMENT_PAGE_SIZE

            # Funnel flow stores only the first page; lazily append more pages on demand.
            if new_offset >= len(results):
                apartments_service = getattr(self, "_apartments_service", None)
                can_fetch_more = (
                    apartment_filters is not None
                    and apartments_service is not None
                    and len(results) < apartment_total_value
                )
                if can_fetch_more:
                    # Qdrant may return None offset while more rows still exist in count().
                    # In that case, fetch a wider prefix from start and replace cached list.
                    backfill_from_start = apartment_next_offset is None
                    scroll_limit = (
                        new_offset + _APARTMENT_PAGE_SIZE
                        if backfill_from_start
                        else _APARTMENT_PAGE_SIZE
                    )
                    scroll_offset = None if backfill_from_start else apartment_next_offset
                    try:
                        (
                            extra_results,
                            total_count,
                            next_offset,
                        ) = await apartments_service.scroll_with_filters(
                            filters=apartment_filters,
                            limit=scroll_limit,
                            offset=scroll_offset,
                        )
                    except Exception:
                        logger.exception("Failed to fetch next results page")
                    else:
                        if extra_results:
                            if backfill_from_start and len(extra_results) >= len(results):
                                results = list(extra_results)
                            else:
                                results = _merge_results(results, extra_results)
                            apartment_total = total_count
                            apartment_total_value = (
                                total_count if isinstance(total_count, int) else len(results)
                            )
                            apartment_next_offset = next_offset
                            await state.update_data(
                                apartment_results=results,
                                apartment_total=apartment_total,
                                apartment_next_offset=apartment_next_offset,
                            )
                if new_offset >= len(results):
                    await callback.answer("Все результаты уже показаны")
                    return
            page = results[new_offset : new_offset + _APARTMENT_PAGE_SIZE]
            for result in page:
                if callback.message:
                    await self._send_property_card(callback.message, result, callback.from_user.id)
            shown = len(page)
            shown_total = new_offset + shown
            total = apartment_total_value
            has_more = shown_total < total
            if callback.message:
                await callback.message.answer(
                    f"Найдено {total} апартаментов (показаны {new_offset + 1}–{shown_total})",
                    reply_markup=build_results_footer(
                        shown_total=shown_total,
                        total=total,
                        has_more=has_more,
                    ),
                )
            await state.update_data(apartment_offset=new_offset)
            await callback.answer()
        elif data == "results:refine":
            await state.update_data(apartment_results=None, apartment_offset=0)
            if callback.message:
                await callback.message.answer(
                    "Опишите, какие апартаменты вы ищете, и я подберу варианты."
                )
            await callback.answer()
        elif data == "results:viewing":
            from .handlers.phone_collector import start_phone_collection

            state_data = await state.get_data()
            results = state_data.get("apartment_results", [])
            # Первые 5 результатов как контекст для CRM заметки
            viewing_objs = []
            for r in results[:5]:
                if isinstance(r, dict):
                    p = r.get("payload", {})
                    viewing_objs.append(
                        {
                            "id": r.get("id", ""),
                            "complex_name": p.get("complex_name", ""),
                            "property_type": p.get("property_type", ""),
                            "area_m2": p.get("area_m2", 0),
                            "price_eur": p.get("price_eur", 0),
                        }
                    )
            await start_phone_collection(
                callback, state, service_key="viewing", viewing_objects=viewing_objs or None
            )
        else:
            await callback.answer()

    async def handle_card_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        dialog_manager: Any = None,
    ) -> None:
        """Handle card action callbacks: card:viewing, card:ask (#722)."""
        from .handlers.phone_collector import start_phone_collection

        data = callback.data or ""
        parts = data.split(":", 2)
        if len(parts) < 3 or not callback.from_user:
            await callback.answer()
            return

        action = parts[1]  # "viewing" or "ask"
        property_id = parts[2]

        state_data = await state.get_data()
        raw_results = state_data.get("apartment_results")
        apt_results = raw_results if isinstance(raw_results, list) else []
        matched = next(
            (r for r in apt_results if isinstance(r, dict) and r.get("id") == property_id),
            None,
        )
        viewing_objects: list[dict] = []
        if matched:
            p = matched.get("payload", {})
            viewing_objects.append(
                {
                    "id": property_id,
                    "complex_name": p.get("complex_name", ""),
                    "property_type": p.get("property_type", ""),
                    "area_m2": p.get("area_m2", 0),
                    "price_eur": p.get("price_eur", 0),
                }
            )
        else:
            favorites_service = getattr(self, "_favorites_service", None)
            if favorites_service is not None:
                fav_items = await favorites_service.list(telegram_id=callback.from_user.id)
                for fav in fav_items:
                    if fav.property_id == property_id:
                        d = fav.property_data
                        viewing_objects.append(
                            {
                                "id": fav.property_id,
                                "complex_name": d.get("complex_name", ""),
                                "property_type": d.get("property_type", ""),
                                "area_m2": d.get("area_m2", 0),
                                "price_eur": d.get("price_eur", 0),
                            }
                        )
                        break

        if action == "viewing":
            if dialog_manager is not None:
                from aiogram_dialog import StartMode

                from .dialogs.states import ViewingSG

                await dialog_manager.start(
                    ViewingSG.date,
                    mode=StartMode.RESET_STACK,
                    data={"selected_objects": viewing_objects},
                )
            else:
                await start_phone_collection(
                    callback,
                    state,
                    service_key="viewing",
                    viewing_objects=viewing_objects or None,
                )
        elif action == "ask":
            await start_phone_collection(
                callback,
                state,
                service_key="manager_question",
                viewing_objects=viewing_objects or None,
            )
        else:
            await callback.answer()

    @observe(name="telegram-rag-query")
    async def handle_query(
        self, message: Message, locale: str = "ru", state: FSMContext | None = None
    ):
        """Handle user query via supervisor graph (#310: supervisor-only)."""
        pipeline_start = time.perf_counter()
        assert message.bot is not None
        assert message.from_user is not None
        bot = message.bot

        # Handoff mode check (#730): relay to topic or skip bot response.
        if self._handoff_state is not None:
            handoff = await self._handoff_state.get_by_client(message.from_user.id)
            if handoff and handoff.mode == "human":
                # Full handoff: relay only, no bot response.
                if self._forum_bridge is not None:
                    await self._forum_bridge.relay_to_topic(
                        from_chat_id=message.chat.id,
                        message_id=message.message_id,
                        topic_id=handoff.topic_id,
                    )
                return
            if handoff and handoff.mode == "human_waiting" and self._forum_bridge is not None:
                # Waiting for manager: relay + continue with normal RAG response.
                await self._forum_bridge.relay_to_topic(
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                    topic_id=handoff.topic_id,
                )

        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        root_trace_metadata: dict[str, Any] = {}
        response_text = await self._handle_query_supervisor(
            message,
            pipeline_start,
            locale=locale,
            root_trace_metadata=root_trace_metadata,
            state=state,
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

    async def _handle_apartment_fast_path(
        self,
        *,
        user_text: str,
        message: Message,
        state: FSMContext | None = None,
    ) -> str | None:
        """C+ fast path: regex filters -> hybrid search -> generate. No agent loop (#629)."""
        from .services.apartment_filter_extractor import ApartmentFilterExtractor
        from .services.apartments_service import check_escalation

        extractor = ApartmentFilterExtractor()
        parsed = extractor.parse(user_text)

        if parsed.confidence == "LOW":
            return None  # escalate to agent

        semantic_query = parsed.semantic_query or user_text
        dense, sparse, colbert = await self._embeddings.aembed_hybrid_with_colbert(semantic_query)
        await self._cache.store_embedding(semantic_query, dense)
        await self._cache.store_sparse_embedding(semantic_query, sparse)

        filters = parsed.to_filters_dict()
        results, returned_count = await self._apartments_service.search_with_filters(
            dense_vector=dense,
            colbert_query=colbert or None,
            sparse_vector=sparse,
            filters=filters or None,
            top_k=10,
        )

        score_spread = (results[0]["score"] - results[-1]["score"]) if len(results) > 1 else 0
        escalation = check_escalation(
            returned_count=returned_count,
            top_k=10,
            score_spread=score_spread,
            confidence=parsed.confidence,
        )
        if escalation:
            return None  # escalate to agent

        from .agents.apartment_tools import _format_apartment_results
        from .services.generate_response import generate_response

        context = _format_apartment_results(results)

        generated = await generate_response(
            query=user_text,
            documents=[],
            retrieved_context=[{"content": context, "source": "apartments_catalog"}],
            raw_messages=[{"role": "user", "content": user_text}],
            config=self._graph_config,
            message=message,
        )

        response_text = str(generated.get("response", "") or context)
        if not generated.get("response_sent"):
            await self._send_markdown_chunks(message, response_text)

        # Store results in FSMContext and send property cards (#654)
        if state is not None and results:
            from .keyboards.property_card import build_results_footer

            await state.update_data(
                apartment_results=results,
                apartment_query=user_text,
                apartment_offset=0,
                bookmarks_context=False,
                apartment_total=len(results),
                apartment_next_offset=None,
                apartment_filters=None,
            )
            page = results[:_APARTMENT_PAGE_SIZE]
            for result in page:
                await self._send_property_card(message, result, message.from_user.id)
            shown = len(page)
            total = len(results)
            await message.answer(
                f"Найдено {total} апартаментов (показаны 1–{shown})",
                reply_markup=build_results_footer(
                    shown_total=shown,
                    total=total,
                    has_more=total > _APARTMENT_PAGE_SIZE,
                ),
            )

        return response_text

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
        state: FSMContext | None = None,
    ) -> str | None:
        """Thin wrapper: delegates to run_client_pipeline (see pipelines/client.py).

        Returns:
            Response text if the pipeline handled the request.
            None if the pipeline signals needs_agent=True (caller falls through to sdk_agent).
        """
        # Apartment fast path: intent check → regex filters → hybrid search → generate (#629)
        from .pipelines.client import detect_agent_intent

        if detect_agent_intent(user_text) == "apartment":
            apt_answer = await self._handle_apartment_fast_path(
                user_text=user_text,
                message=message,
                state=state,
            )
            if apt_answer is not None:
                return apt_answer
            return None  # escalate to agent path

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
        state: FSMContext | None = None,
    ) -> str:
        """Handle query via create_agent SDK (#413 — replaces build_supervisor_graph)."""
        from .agents.agent import LOCALE_TO_LANGUAGE
        from .agents.apartment_tools import apartment_search
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
        pre_agent_start = time.perf_counter()

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
                        wall_ms = (time.perf_counter() - pipeline_start) * 1000
                        lf = get_client()
                        tid = lf.get_current_trace_id() or ""
                        lf.update_current_trace(
                            input={"query": user_text},
                            output={"response": _BLOCKED_RESPONSE},
                            metadata={
                                "pipeline_mode": "sdk_agent",
                                "pipeline_wall_ms": wall_ms,
                                "e2e_latency_ms": wall_ms,
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
                                    "pipeline_wall_ms": wall_ms,
                                    "e2e_latency_ms": wall_ms,
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
                    embed_start = time.perf_counter()
                    embedding = await self._cache.get_embedding(user_text)
                    sparse = await self._cache.get_sparse_embedding(user_text)
                    colbert = None
                    if embedding is None:
                        _has_hybrid_colbert = callable(
                            getattr(self._embeddings, "aembed_hybrid_with_colbert", None)
                        ) and asyncio.iscoroutinefunction(
                            self._embeddings.aembed_hybrid_with_colbert
                        )
                        _has_hybrid = callable(
                            getattr(self._embeddings, "aembed_hybrid", None)
                        ) and asyncio.iscoroutinefunction(self._embeddings.aembed_hybrid)
                        if _has_hybrid_colbert:
                            (
                                embedding,
                                sparse,
                                colbert,
                            ) = await self._embeddings.aembed_hybrid_with_colbert(user_text)
                            await self._cache.store_embedding(user_text, embedding)
                            await self._cache.store_sparse_embedding(user_text, sparse)
                            rag_result_store["cache_key_colbert"] = colbert
                        elif _has_hybrid:
                            embedding, sparse = await self._embeddings.aembed_hybrid(user_text)
                            await self._cache.store_embedding(user_text, embedding)
                            await self._cache.store_sparse_embedding(user_text, sparse)
                        else:
                            embedding = await self._embeddings.aembed_query(user_text)
                            await self._cache.store_embedding(user_text, embedding)
                    else:
                        # Embedding cached but sparse may have expired (#637)
                        if sparse is None:
                            _has_hybrid_colbert = callable(
                                getattr(self._embeddings, "aembed_hybrid_with_colbert", None)
                            ) and asyncio.iscoroutinefunction(
                                self._embeddings.aembed_hybrid_with_colbert
                            )
                            _has_hybrid = callable(
                                getattr(self._embeddings, "aembed_hybrid", None)
                            ) and asyncio.iscoroutinefunction(self._embeddings.aembed_hybrid)
                            if _has_hybrid_colbert:
                                (
                                    _,
                                    sparse,
                                    colbert,
                                ) = await self._embeddings.aembed_hybrid_with_colbert(user_text)
                                await self._cache.store_sparse_embedding(user_text, sparse)
                            elif _has_hybrid:
                                _, sparse = await self._embeddings.aembed_hybrid(user_text)
                                await self._cache.store_sparse_embedding(user_text, sparse)
                    rag_result_store["pre_agent_embed_ms"] = (
                        time.perf_counter() - embed_start
                    ) * 1000
                    check_start = time.perf_counter()
                    cached = await self._cache.check_semantic(
                        query=user_text,
                        vector=embedding,
                        query_type=query_type,
                        cache_scope="rag",
                        agent_role=role,
                    )
                    rag_result_store["pre_agent_cache_check_ms"] = (
                        time.perf_counter() - check_start
                    ) * 1000
                    if cached:
                        logger.info("Pre-agent cache HIT (type=%s): %.60s", query_type, user_text)
                        rag_result_store["cache_hit"] = True
                        rag_result_store["query_type"] = query_type
                        rag_result_store["cache_key_embedding"] = embedding
                        rag_result_store["cache_key_sparse"] = sparse
                        # Write Langfuse scores and trace metadata
                        lf = get_client()
                        pre_agent_ms = (time.perf_counter() - pre_agent_start) * 1000
                        rag_result_store["pre_agent_ms"] = pre_agent_ms
                        tid = lf.get_current_trace_id() or ""
                        reply_markup = None
                        if tid and query_type not in _NO_RAG_QUERY_TYPES:
                            from telegram_bot.feedback import build_feedback_keyboard

                            reply_markup = build_feedback_keyboard(tid)
                        await self._send_markdown_chunks(
                            message,
                            str(cached),
                            reply_markup=reply_markup,
                        )
                        wall_ms = (time.perf_counter() - pipeline_start) * 1000
                        lf.update_current_trace(
                            input={"query": user_text},
                            output={"response": cached},
                            metadata={
                                "pipeline_mode": "pre_agent_cache",
                                "pipeline_wall_ms": wall_ms,
                                "pre_agent_ms": pre_agent_ms,
                                "pre_agent_embed_ms": rag_result_store.get("pre_agent_embed_ms"),
                                "pre_agent_cache_check_ms": rag_result_store.get(
                                    "pre_agent_cache_check_ms"
                                ),
                                "e2e_latency_ms": wall_ms,
                            },
                        )
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
                        if root_trace_metadata is not None:
                            root_trace_metadata.update(
                                {
                                    "pipeline_mode": "pre_agent_cache",
                                    "pipeline_wall_ms": wall_ms,
                                    "pre_agent_ms": pre_agent_ms,
                                    "pre_agent_embed_ms": rag_result_store.get(
                                        "pre_agent_embed_ms"
                                    ),
                                    "pre_agent_cache_check_ms": rag_result_store.get(
                                        "pre_agent_cache_check_ms"
                                    ),
                                    "e2e_latency_ms": wall_ms,
                                }
                            )
                        return cached
                    # MISS: stash all embeddings so rag_pipeline can skip recomputation (#571)
                    logger.debug("Pre-agent cache MISS (type=%s): %.60s", query_type, user_text)
                    rag_result_store["cache_key_embedding"] = embedding
                    rag_result_store["cache_key_sparse"] = sparse
                    rag_result_store["query_type"] = query_type
                    # Compute colbert if not yet available to avoid double embed in rag_pipeline (#634)
                    if colbert is None:
                        _has_colbert_only = callable(
                            getattr(self._embeddings, "aembed_colbert_query", None)
                        ) and asyncio.iscoroutinefunction(self._embeddings.aembed_colbert_query)
                        if _has_colbert_only:
                            try:
                                colbert = await self._embeddings.aembed_colbert_query(user_text)
                            except Exception:
                                logger.debug("Pre-agent ColBERT encode failed, skipping")
                    rag_result_store["cache_key_colbert"] = colbert
                except Exception:
                    logger.warning(
                        "Pre-agent cache check failed, proceeding to agent", exc_info=True
                    )

            rag_result_store.setdefault(
                "pre_agent_ms", (time.perf_counter() - pre_agent_start) * 1000
            )

            if role == "client" and self.config.client_direct_pipeline_enabled:
                try:
                    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                        rag_result_store["pre_agent_ms"] = (
                            time.perf_counter() - pre_agent_start
                        ) * 1000
                        if root_trace_metadata is not None:
                            root_trace_metadata.update(
                                {
                                    "pipeline_mode": "client_direct",
                                    "pre_agent_ms": rag_result_store["pre_agent_ms"],
                                }
                            )
                        pipeline_answer = await self._handle_client_direct_pipeline(
                            message=message,
                            user_text=user_text,
                            user_id=user_id,
                            session_id=session_id,
                            role=role,
                            query_type=query_type,
                            rag_result_store=rag_result_store,
                            state=state,
                        )
                        if pipeline_answer is not None:
                            if root_trace_metadata is not None:
                                root_trace_metadata.update(
                                    {
                                        "pipeline_wall_ms": rag_result_store.get(
                                            "pipeline_wall_ms"
                                        ),
                                        "e2e_latency_ms": rag_result_store.get("e2e_latency_ms"),
                                    }
                                )
                            return pipeline_answer
                        # needs_agent=True: fall through to sdk_agent path below
                except Exception:
                    logger.exception(
                        "Client direct pipeline failed; falling back to sdk_agent",
                    )

            # Build base tools list (client-only: rag_search)
            base_tools: list[Any] = [rag_search, apartment_search]

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
                apartments_service=self._apartments_service,
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
            pre_agent_ms = float(rag_result_store.get("pre_agent_ms", 0.0) or 0.0)

            # Write Langfuse trace metadata
            lf = get_client()
            lf.update_current_trace(
                input={"query": message.text},
                metadata={
                    "pipeline_mode": "sdk_agent",
                    "pipeline_wall_ms": wall_ms,
                    "pre_agent_ms": pre_agent_ms,
                    "pre_agent_embed_ms": rag_result_store.get("pre_agent_embed_ms"),
                    "pre_agent_cache_check_ms": rag_result_store.get("pre_agent_cache_check_ms"),
                    "e2e_latency_ms": wall_ms,
                },
            )
            if root_trace_metadata is not None:
                root_trace_metadata.update(
                    {
                        "pipeline_mode": "sdk_agent",
                        "pipeline_wall_ms": wall_ms,
                        "pre_agent_ms": pre_agent_ms,
                        "pre_agent_embed_ms": rag_result_store.get("pre_agent_embed_ms"),
                        "pre_agent_cache_check_ms": rag_result_store.get(
                            "pre_agent_cache_check_ms"
                        ),
                        "e2e_latency_ms": wall_ms,
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
            result["e2e_latency_ms"] = result["pipeline_wall_ms"]
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
        from .agents.apartment_tools import apartment_search
        from .agents.rag_tool import rag_search
        from .agents.utility_tools import get_utility_tools

        role = await self._resolve_user_role(user_id)
        session_id = make_session_id("chat", chat_id)

        base_tools: list[Any] = [rag_search, apartment_search]
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
            apartments_service=self._apartments_service,
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
            "search": "Search + Rerank cache",
            "rerank": "Rerank cache",
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
        from .agents.apartment_tools import apartment_search
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
        base_tools: list[Any] = [rag_search, apartment_search]
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
            apartments_service=self._apartments_service,
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
                from .services.kommo_tokens import REDIS_KEY, KommoTokenStore

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
                    should_init_kommo = True
                    if auth_code is None:
                        existing = await self._cache.redis.hgetall(REDIS_KEY)
                        if not existing:
                            env_token = self.config.kommo_access_token.get_secret_value()
                            if env_token:
                                await token_store.seed_env_token(env_token)
                                logger.info(
                                    "Kommo: seeded access token from KOMMO_ACCESS_TOKEN env var"
                                )
                            else:
                                logger.info(
                                    "Kommo CRM disabled: no stored tokens and no KOMMO_AUTH_CODE "
                                    "(set env var for first-time setup)"
                                )
                                self._kommo_client = None
                                should_init_kommo = False

                    if should_init_kommo:
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

            test_conn: Any | None = None
            try:
                # Validate DB exists before creating pool (avoid traceback spam #570)
                test_conn = await asyncpg.connect(self.config.realestate_database_url, timeout=5)
            except asyncpg.InvalidCatalogNameError:
                target_db = self._extract_database_name(self.config.realestate_database_url)
                if target_db is None:
                    raise
                logger.warning(
                    "PostgreSQL database %s missing; attempting auto-create",
                    target_db,
                )
                if not await self._ensure_postgres_database_exists(asyncpg, target_db):
                    raise
                test_conn = await asyncpg.connect(self.config.realestate_database_url, timeout=5)
            finally:
                if test_conn is not None:
                    await test_conn.close()

            self._pg_pool = await asyncpg.create_pool(
                self.config.realestate_database_url,
                min_size=0,
                max_size=5,
                timeout=5,
            )
            logger.info("PostgreSQL pool ready (realestate)")
            await self._ensure_realestate_schema()
            logger.info("PostgreSQL schema ready (realestate)")

            from .services.user_service import UserService

            self._user_service = UserService(pool=self._pg_pool)

            # Initialize lead scoring store (#384)
            from .services.lead_scoring_store import LeadScoringStore

            self._lead_scoring_store = LeadScoringStore(pool=self._pg_pool)
            logger.info("Lead scoring store ready")

            # Initialize favorites service (#628)
            from .services.favorites_service import FavoritesService

            self._favorites_service = FavoritesService(pool=self._pg_pool)
            logger.info("Favorites service ready")

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

        # Initialize AI Advisor service (#697)
        self._ai_advisor_service: Any | None = None
        if self._kommo_client is not None:
            try:
                from .services.ai_advisor_service import AIAdvisorService

                self._ai_advisor_service = AIAdvisorService(
                    kommo_client=self._kommo_client,
                    llm=self._llm,
                    cache=self._cache,
                )
                logger.info("AIAdvisorService initialized")
            except Exception:
                logger.exception("Failed to initialize AIAdvisorService")

        # Cache bot user id for echo-skip in group handlers (#730 review)
        try:
            me = await self.bot.me()
            self._bot_user_id = me.id
        except Exception:
            logger.warning("Failed to cache bot user id")

        # Initialize handoff services (#730)
        if self._cache.redis is not None:
            self._handoff_state = HandoffState(
                self._cache.redis,
                ttl_hours=self.config.handoff_ttl_hours,
            )
            if self.config.managers_group_id:
                self._forum_bridge = ForumBridge(
                    bot=self.bot,
                    managers_group_id=self.config.managers_group_id,
                )
                logger.info(
                    "Forum Topics bridge enabled (managers_group_id=%s)",
                    self.config.managers_group_id,
                )

        # Initialize i18n (fluentogram)
        from .middlewares.i18n import create_translator_hub, setup_i18n_middleware

        if self._i18n_hub is None:
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
            ai_advisor_service=self._ai_advisor_service,
        )
        logger.info("i18n middleware ready")

        # Setup aiogram-dialog (#658: removed dead client_menu_dialog)
        from aiogram_dialog import setup_dialogs as aiogram_setup_dialogs

        from .dialogs.crm_ai_advisor import advisor_dialog
        from .dialogs.crm_contacts import (
            contacts_menu_dialog,
            create_contact_dialog,
            search_contacts_dialog,
        )
        from .dialogs.crm_leads import (
            create_lead_dialog,
            leads_menu_dialog,
            my_leads_dialog,
            search_leads_dialog,
        )
        from .dialogs.crm_notes import create_note_dialog
        from .dialogs.crm_tasks import create_task_dialog, my_tasks_dialog, tasks_menu_dialog
        from .dialogs.faq import faq_dialog
        from .dialogs.funnel import funnel_dialog
        from .dialogs.manager_menu import manager_menu_dialog
        from .dialogs.settings import settings_dialog
        from .dialogs.viewing import viewing_dialog
        from .handlers.crm_callbacks import create_crm_router

        # CRM card inline callbacks (crm:* prefix) — before aiogram-dialog setup (#697)
        self.dp.include_router(create_crm_router())

        self.dp.include_router(manager_menu_dialog)
        self.dp.include_router(leads_menu_dialog)
        self.dp.include_router(create_lead_dialog)
        self.dp.include_router(my_leads_dialog)
        self.dp.include_router(search_leads_dialog)
        self.dp.include_router(contacts_menu_dialog)
        self.dp.include_router(create_contact_dialog)
        self.dp.include_router(search_contacts_dialog)
        self.dp.include_router(tasks_menu_dialog)
        self.dp.include_router(create_task_dialog)
        self.dp.include_router(my_tasks_dialog)
        self.dp.include_router(create_note_dialog)
        self.dp.include_router(advisor_dialog)
        self.dp.include_router(settings_dialog)
        self.dp.include_router(funnel_dialog)
        self.dp.include_router(faq_dialog)
        self.dp.include_router(viewing_dialog)
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

        # Set default Menu Button → opens commands list (#628)
        from aiogram.types import MenuButtonCommands

        await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

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
