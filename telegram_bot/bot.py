"""Main Telegram bot logic — legacy graph pipeline.

Module-level helpers were extracted to focused submodules in slice 1 of
the ``PropertyBot`` decomposition (issue #1265 / #2046). The thin
wrappers below preserve the historical ``from telegram_bot.bot import X``
import surface for tests that ``patch("telegram_bot.bot.X", ...)``.

Slice 1 extraction map:

* ``_bot_state_helpers`` (#1265 PR-1) — apartment-list and catalog-control
  message-id reads (``_state_apartment_results``,
  ``_state_control_message_id``, ``_extract_current_turn``).
* ``_bot_observability`` (#1265 PR-2) — Langfuse trace metadata builder
  and voice error-score writer (``_build_trace_metadata``,
  ``_write_voice_error_scores``).
* ``_bot_error_classification`` (#1265 PR-3) — post-pipeline cleanup and
  checkpointer error guards (``_is_post_pipeline_cleanup_error``,
  ``_is_checkpointer_runtime_error``).
* ``_bot_streaming`` (#1265 PR-4) — agent streaming draft helpers
  (``_new_draft_id``, ``_extract_stream_chunk_text``,
  ``_stream_agent_to_draft``, ``_AGENT_DRAFT_INTERVAL``).
* ``_bot_pre_agent`` (#1265 PR-5) — pre-agent state contract, dense
  vector caching, retrieval-vector preparation
  (``_build_pre_agent_state_contract``, ``_has_async_method``,
  ``_get_or_compute_pre_agent_dense``,
  ``_prepare_pre_agent_retrieval_vectors``).

Each extraction is enforced by a contract test under
``tests/contract/test_bot_*_extraction_contract.py``: byte-for-byte
parity with the previous module-level implementation, plus a
``from telegram_bot.bot import …`` import surface guard.

The remaining lifecycle method extraction (``PropertyBot`` instance
methods → focused modules) is tracked separately as #2048 and is
blocked on the runtime migration in #1948 / #2045 / #2047.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import socket
import time
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    Message,
)
from aiogram.utils.chat_action import ChatActionSender

from src.runtime.integrations.polling_lock import POLLING_LOCK_KEY, RedisPollingLock
from src.services.handoff_state import HandoffData, HandoffState

from . import (
    _bot_catalog,  # #2816 Slice 2: extracted catalog/card handlers
    _bot_error_classification,  # #1265 Slice 1 PR-3: extracted error-classification helpers
    _bot_favorites,  # #2816 Slice 2: extracted favorites handlers
    _bot_feedback_handlers,  # #2048 PR-9a: extracted feedback callback handlers
    _bot_handoff,  # #2816 Slice 2: extracted handoff handlers
    _bot_lifecycle,  # #1265 Slice 2 PR-8 / #2048: extracted lifecycle helpers
    _bot_observability,  # #1265 Slice 1 PR-2: extracted observability helpers
    _bot_pre_agent,  # #1265 Slice 1 PR-5: extracted pre-agent helpers
    _bot_query_pipeline,  # #2816 Slice 2: extracted query pipeline handlers
    _bot_state_helpers,  # #1265 Slice 1 PR-1: extracted state-shape helpers
    _bot_streaming,  # #1265 Slice 1 PR-4: extracted streaming helpers
)
from .callback_data import FavoriteCB, FeedbackCB, FeedbackReasonCB, ResultsCB
from .config import BotConfig
from .constants import (
    split_telegram_response as _split_telegram_response,
)
from .integrations.memory import (
    begin_checkpoint_overhead_capture,
    end_checkpoint_overhead_capture,
    sum_checkpoint_overhead_ms,
)
from .keyboards.client_keyboard import (
    parse_menu_button,
)
from .middlewares import setup_error_handler, setup_throttling_middleware
from .middlewares.fsm_cancel import FSMCancelMiddleware
from .middlewares.langfuse_middleware import LangfuseContextMiddleware
from .observability import (
    create_callback_handler,
    get_client,
    get_langfuse_client,  # noqa: F401 — re-export kept so legacy tests can patch telegram_bot.bot.get_langfuse_client (#2048 PR-9a)
    observe,
    propagate_attributes,
)
from .observability_payloads import build_safe_input_payload, build_safe_output_payload
from .scoring import (
    compute_checkpointer_overhead_proxy_ms,
    write_langfuse_scores,
)
from .services.forum_bridge import ForumBridge
from .services.redis_monitor import RedisHealthMonitor
from .startup_status import StartupReport, StartupSeverity, StartupSignal


class GraphRecursionError(RuntimeError):
    """Compatibility exception after legacy graph removal."""


if TYPE_CHECKING:
    from .agents.context import BotContext as BotContextType
    from .pipelines.state_contract import PreAgentStateContract
    from .services.history_service import HistoryService
else:
    BotContextType = Any

# Keep a patchable module-level symbol for tests without importing qdrant-heavy code.
HistoryService: Any = None  # type: ignore[no-redef]
AsyncQdrantClient: Any = None
BotContext: Any = Any


logger = logging.getLogger(__name__)

# --- Checkpoint namespace constants (versioned for safe migration) ---
_CHECKPOINT_NS_VOICE = "tg:voice:v1"
_FEEDBACK_CONFIRMATION_TTL_S = 5.0
_APARTMENT_PAGE_SIZE = 5
_NO_RAG_QUERY_TYPES: frozenset[str] = frozenset({"CHITCHAT", "OFF_TOPIC"})
# Heartbeat runs every ttl/3, so a third consecutive miss can consume the full lease.
_POLLING_LOCK_MAX_REFRESH_FAILURES = 2


def create_bot_agent(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from .agents.agent import create_bot_agent as _create_bot_agent

    return _create_bot_agent(*args, **kwargs)


def build_graph(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from .pipelines.graph_compat import build_graph as _build_graph

    return _build_graph(*args, **kwargs)


def classify_query(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from src.runtime.graph.nodes.classify import classify_query as _classify_query

    return _classify_query(*args, **kwargs)


def detect_injection(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from src.runtime.graph.nodes.guard import detect_injection as _detect_injection

    return _detect_injection(*args, **kwargs)


def _build_pre_agent_state_contract(
    *,
    rag_result_store: dict[str, Any],
    query_type: str,
    topic_hint: str | None,
    dense_vector: list[float] | None,
    sparse_vector: dict[str, Any] | None,
    colbert_query: list[list[float]] | None,
    grounding_mode: str,
    filters: dict[str, Any] | None = None,
) -> PreAgentStateContract:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    return _bot_pre_agent._build_pre_agent_state_contract(
        rag_result_store=rag_result_store,
        query_type=query_type,
        topic_hint=topic_hint,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        colbert_query=colbert_query,
        grounding_mode=grounding_mode,
        filters=filters,
    )


def _has_async_method(obj: Any, name: str) -> bool:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    return _bot_pre_agent._has_async_method(obj, name)


async def _get_or_compute_pre_agent_dense(
    cache: Any,
    embeddings: Any,
    query: str,
    result_store: dict[str, Any],
) -> list[float] | None:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    return await _bot_pre_agent._get_or_compute_pre_agent_dense(
        cache=cache,
        embeddings=embeddings,
        query=query,
        result_store=result_store,
    )


async def _prepare_pre_agent_retrieval_vectors(
    cache: Any,
    embeddings: Any,
    query: str,
    dense: list[float] | None,
    result_store: dict[str, Any],
) -> None:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    await _bot_pre_agent._prepare_pre_agent_retrieval_vectors(
        cache=cache,
        embeddings=embeddings,
        query=query,
        dense=dense,
        result_store=result_store,
    )


def _new_draft_id() -> int:
    """Thin wrapper — see ``_bot_streaming`` (#1265 Slice 1 PR-4)."""
    return _bot_streaming._new_draft_id()


_AGENT_DRAFT_INTERVAL = _bot_streaming._AGENT_DRAFT_INTERVAL


async def _stream_agent_to_draft(
    agent: Any,
    payload: dict[str, Any],
    config: dict[str, Any],
    bot: Any,
    chat_id: int,
    thread_id: int | None = None,
) -> dict[str, Any]:
    """Thin wrapper — see ``_bot_streaming`` (#1265 Slice 1 PR-4)."""
    return await _bot_streaming._stream_agent_to_draft(
        agent=agent,
        payload=payload,
        config=config,
        bot=bot,
        chat_id=chat_id,
        thread_id=thread_id,
        draft_interval=_AGENT_DRAFT_INTERVAL,
    )


def _state_apartment_results(state_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Read cached apartment payloads from legacy or dialog-owned state.

    Implementation lives in :mod:`telegram_bot._bot_state_helpers` (#1265 Slice 1
    PR-1). This wrapper preserves the historical ``telegram_bot.bot`` import
    surface for existing callers and tests.
    """
    return _bot_state_helpers._state_apartment_results(state_data)


def _state_control_message_id(state_data: dict[str, Any]) -> int | None:
    """Locate the catalog control message id (legacy or dialog-owned shape).

    Re-exported from :mod:`telegram_bot._bot_state_helpers` (#1265 Slice 1 PR-1).
    """
    return _bot_state_helpers._state_control_message_id(state_data)


# Re-export from shared module (avoid circular imports with middlewares)
# Re-export checkpointer helpers from shared utility module for backward compat
from .services.checkpointer_utils import (  # noqa: E402
    _delete_checkpointer_thread as _delete_checkpointer_thread,
)
from .services.checkpointer_utils import (  # noqa: E402
    _supervisor_thread_id as _supervisor_thread_id,
)
from .tracing_context import make_session_id as make_session_id  # noqa: E402


def _extract_current_turn(messages: list[Any]) -> list[Any]:
    """Slice agent checkpointer history down to the current turn (#507).

    Re-exported from :mod:`telegram_bot._bot_state_helpers` (#1265 Slice 1 PR-1).
    """
    return _bot_state_helpers._extract_current_turn(messages)


def _build_trace_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Build shared metadata dict for Langfuse trace (text + voice handlers).

    Re-exported from :mod:`telegram_bot._bot_observability` (#1265 Slice 1 PR-2).
    """
    return _bot_observability._build_trace_metadata(result)


def _write_voice_error_scores(
    lf: Any,
    *,
    trace_id: str = "",
    voice_duration_s: float | None = None,
    error_reason: str = "pipeline_error",
) -> None:
    """Write minimal Langfuse scores for voice traces that exit early (error paths).

    Re-exported from :mod:`telegram_bot._bot_observability` (#1265 Slice 1 PR-2).
    """
    _bot_observability._write_voice_error_scores(
        lf,
        trace_id=trace_id,
        voice_duration_s=voice_duration_s,
        error_reason=error_reason,
    )


def _is_post_pipeline_cleanup_error(exc: Exception) -> bool:
    """Thin wrapper — see ``_bot_error_classification`` (#1265 Slice 1 PR-3)."""
    return _bot_error_classification._is_post_pipeline_cleanup_error(exc)


def _is_checkpointer_runtime_error(exc: Exception) -> bool:
    """Thin wrapper — see ``_bot_error_classification`` (#1265 Slice 1 PR-3)."""
    return _bot_error_classification._is_checkpointer_runtime_error(exc)


def _extract_stream_chunk_text(message_chunk: Any) -> str:
    """Thin wrapper — see ``_bot_streaming`` (#1265 Slice 1 PR-4)."""
    return _bot_streaming._extract_stream_chunk_text(message_chunk)


class PropertyBot:
    """Telegram bot for domain-specific search (configurable via BOT_DOMAIN)."""

    def __init__(self, config: BotConfig):
        """Initialize bot with services."""
        from src.runtime.graph.config import GraphConfig

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

        # Initialize legacy graph service dependencies
        from src.runtime.integrations.cache import CacheLayerManager
        from src.runtime.integrations.embeddings import BGEM3HybridEmbeddings, BGEM3SparseEmbeddings
        from src.runtime.services.qdrant import QdrantService

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

        # Rerank provider (feature flag). "colbert" keeps the existing
        # server-side Qdrant ColBERT path and does not instantiate the
        # deprecated client-side reranker service.
        self._reranker = None
        if config.rerank_provider == "colbert":
            logger.info("Reranking via server-side Qdrant ColBERT path")
        elif config.rerank_provider == "none":
            logger.info("Reranking disabled")

        # LLM (optional, defaults via GraphConfig.create_llm)
        self._llm = self._graph_config.create_llm()

        # Apartment extraction pipeline: LLM first → regex fallback
        from .services.apartment_extraction_pipeline import ApartmentExtractionPipeline
        from .services.apartment_filter_extractor import ApartmentFilterExtractor

        _apt_llm = None
        try:
            from .services.apartment_llm_extractor import ApartmentLlmExtractor

            _apt_llm = ApartmentLlmExtractor(llm=self._llm, model=config.apartment_extraction_model)
        except (ImportError, ModuleNotFoundError):
            logger.warning(
                "ApartmentLlmExtractor unavailable, falling back to regex-only extraction",
                exc_info=True,
            )

        self._apartment_pipeline = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=_apt_llm,
            redis=self._cache.redis,
        )
        # Redis health monitor (periodic background task)
        self._redis_monitor = RedisHealthMonitor(redis_url=config.redis_url)

        # Conversation memory checkpointer (initialized in start())
        self._checkpointer: Any = None

        # Agent checkpointer — Redis with TTL (#424).
        # HumanMessage serialization fixed in langgraph-checkpoint-redis>=0.3.6 (#420).
        self._agent_checkpointer: Any = None

        # History service (initialized in start())
        self._history_service: HistoryService | None = None
        self._history_rest_client: Any = None

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

        # Favorites service (initialized in start() with pg_pool)
        self._favorites_service: Any = None

        # Search event store (initialized in start() with pg_pool)
        self._search_event_store: Any | None = None

        # Handoff services (Forum Topics bridge + Redis state machine)
        self._handoff_state: HandoffState | None = None
        self._forum_bridge: ForumBridge | None = None
        self._bot_user_id: int | None = None

        # Expert topic manager (chat_id+expert_id → thread_id mapping)
        self._topics_enabled: bool = False
        self._deeplink_redis: Any | None = None
        self._topic_manager: Any = None
        self._miniapp_subscriber_task: asyncio.Task[None] | None = None
        self._polling_lock: RedisPollingLock | None = None
        self._polling_lock_task: asyncio.Task[None] | None = None
        self._polling_lock_consecutive_failures: int = 0
        self._polling_lock_owner: str | None = None

        # Bounded fan-out for fire-and-forget history persistence (#1600).
        # Without a bound the text path could accumulate unbounded background
        # tasks under burst traffic / slow DB writes. Track every spawned save
        # so shutdown can drain them; reject new saves with a Langfuse signal
        # once the in-flight count reaches `_history_save_max_concurrency`.
        self._history_save_tasks: set[asyncio.Task[None]] = set()
        self._history_save_max_concurrency: int = int(
            os.getenv("HISTORY_SAVE_MAX_CONCURRENCY", "32")
        )
        self._history_save_drain_timeout_s: float = float(
            os.getenv("HISTORY_SAVE_DRAIN_TIMEOUT_S", "5.0")
        )

        # Track initialization state
        self._cache_initialized = False
        self._pre_agent_filter_extractor: Any | None = None

        # Setup middlewares (before handlers)
        self._setup_middlewares()

        # Register handlers
        self._register_handlers()

    def _spawn_history_save(
        self, coro: Coroutine[Any, Any, None], *, user_id: int | str
    ) -> asyncio.Task[None] | None:
        """Track and bound fan-out for fire-and-forget history persistence (#1600).

        Without a bound the text path could accumulate unbounded background
        tasks under burst traffic / slow DB writes. This helper:

        * rejects the save and logs/scores ``history_save_dropped=1`` once the
          in-flight count reaches ``_history_save_max_concurrency``;
        * tracks every spawned task in ``_history_save_tasks`` so ``stop()``
          can drain them with a bounded timeout.

        Returns the spawned task on success, ``None`` if dropped.
        """
        if len(self._history_save_tasks) >= self._history_save_max_concurrency:
            logger.warning(
                "history-save fan-out at limit (%d in flight); dropping save for user_id=%s",
                self._history_save_max_concurrency,
                user_id,
            )
            lf = get_client()
            if lf is not None:
                try:
                    tid = lf.get_current_trace_id() or ""
                    if tid:
                        lf.create_score(
                            trace_id=tid,
                            name="history_save_dropped",
                            value=1,
                            data_type="BOOLEAN",
                            score_id=f"{tid}-history_save_dropped",
                        )
                except Exception:
                    logger.warning("Failed to write history-save drop score", exc_info=True)
            # Close the unscheduled coroutine so we do not leak a "never awaited" warning.
            close = getattr(coro, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
            return None

        task = asyncio.create_task(coro, name=f"history-save-{user_id}")
        self._history_save_tasks.add(task)
        task.add_done_callback(self._history_save_tasks.discard)
        return task

    def _get_pre_agent_filter_extractor(self) -> Any:
        """Lazily construct the deterministic extractor used on pre-agent semantic misses."""
        if self._pre_agent_filter_extractor is None:
            from .services.apartment_filter_extractor import ApartmentFilterExtractor

            self._pre_agent_filter_extractor = ApartmentFilterExtractor()
        return self._pre_agent_filter_extractor

    async def _extract_pre_agent_filters(self, query: str) -> dict[str, Any]:
        """Extract structured retrieval filters for the active bot path."""
        try:
            extractor = self._get_pre_agent_filter_extractor()
            filters = extractor.extract_filters(query)
        except Exception:
            logger.warning("Pre-agent filter extraction failed, continuing without filters")
            return {}
        return dict(filters) if isinstance(filters, dict) else {}

    def _setup_middlewares(self):
        """Setup bot middlewares."""
        # Langfuse context must be outermost to wrap all handlers
        self.dp.message.outer_middleware(LangfuseContextMiddleware())
        self.dp.callback_query.outer_middleware(LangfuseContextMiddleware())
        setup_throttling_middleware(self.dp, default_rate=1.0, admin_ids=self.config.admin_ids)
        setup_error_handler(self.dp)
        self.dp.message.outer_middleware(FSMCancelMiddleware())
        logger.info("Middlewares configured")

    @staticmethod
    def _extract_database_name(database_url: str) -> str | None:
        """Extract database name from PostgreSQL URL.

        Thin wrapper — canonical impl lives in
        :mod:`telegram_bot._bot_postgres_bootstrap` (#1265).
        """
        from telegram_bot._bot_postgres_bootstrap import extract_database_name

        return extract_database_name(database_url)

    async def _ensure_postgres_database_exists(
        self, asyncpg_module: Any, database_name: str
    ) -> bool:
        """Ensure target PostgreSQL database exists, creating it when missing.

        Thin wrapper — canonical impl lives in
        :mod:`telegram_bot._bot_postgres_bootstrap` (#1265).
        """
        from telegram_bot._bot_postgres_bootstrap import ensure_postgres_database_exists

        return await ensure_postgres_database_exists(
            asyncpg_module,
            self.config.realestate_database_url,
            database_name,
        )

    async def _ensure_realestate_schema(self) -> None:
        """Idempotent bootstrap for realestate runtime tables.

        Thin wrapper — canonical impl lives in
        :mod:`telegram_bot._bot_postgres_bootstrap` (#1265).
        """
        from telegram_bot._bot_postgres_bootstrap import ensure_realestate_schema

        await ensure_realestate_schema(self._pg_pool)

    def _register_handlers(self):
        """Register message handlers."""
        # Phone collector FSM — include before catch-all handlers (#628)
        from .handlers.phone_collector import create_phone_router

        self.dp.include_router(create_phone_router())

        # Group message handler — manager → client relay (#730)
        if self.config.managers_group_id:
            self.dp.message(
                F.chat.id == self.config.managers_group_id,
                F.message_thread_id,
            )(self._handle_group_message)

        # Command handlers Router (extracted from class methods)
        from .handlers.command_handlers import create_commands_router

        self.dp.include_router(create_commands_router(self))
        self.dp.message(
            StateFilter(None),
            F.voice,
            flags={"rate_limit": {"rate": 3.5, "key": "voice"}},
        )(self.handle_voice)
        from .keyboards.client_keyboard import get_menu_button_texts

        menu_button_texts = tuple(get_menu_button_texts(self._i18n_hub))
        self.dp.message(
            F.text.in_(menu_button_texts),
            flags={"rate_limit": {"rate": 0.6, "key": "menu"}},
        )(self.handle_menu_button)
        # NOTE: catch-all handle_query is registered on self._catch_all_router
        # which is included AFTER dialog routers in _setup_dialogs().
        # This ensures dialog MessageInput (e.g. viewing phone input)
        # is resolved before the catch-all (aiogram SDK: first-match wins).
        # Demo flow router
        from .handlers.demo_handler import create_demo_router

        self.dp.include_router(create_demo_router())

        self.dp.callback_query(FeedbackCB.filter())(self.handle_feedback)
        # Legacy buttons in old chat history may contain "fb:done" (without trailing ':').
        self.dp.callback_query(F.data == "fb:done")(self.handle_feedback)
        self.dp.callback_query(FeedbackReasonCB.filter())(self.handle_feedback_reason)
        self.dp.callback_query(F.data.startswith("hitl:"))(self.handle_hitl_callback)
        self.dp.callback_query(F.data.startswith("cc:"))(self.handle_clearcache_callback)
        # Client menu inline callbacks (#628)
        self.dp.callback_query(F.data.startswith("svc:"))(self.handle_service_callback)
        self.dp.callback_query(F.data.startswith("cta:"))(self.handle_cta_callback)
        self.dp.callback_query(FavoriteCB.filter(F.action == "add"))(self.handle_fav_add)
        self.dp.callback_query(FavoriteCB.filter(F.action == "remove"))(self.handle_fav_remove)
        self.dp.callback_query(FavoriteCB.filter(F.action == "viewing"))(self.handle_fav_viewing)
        self.dp.callback_query(FavoriteCB.filter(F.action == "viewing_all"))(
            self.handle_fav_viewing_all
        )
        # Legacy buttons in old chat history may contain "fav:viewing_all" (without id part).
        self.dp.callback_query(F.data == "fav:viewing_all")(self.handle_favorite_callback)
        self.dp.callback_query(ResultsCB.filter())(self.handle_results_callback)
        self.dp.callback_query(F.data.startswith("card:"))(self.handle_card_callback)
        self.dp.callback_query(F.data.startswith("ask:"))(self.handle_ask_callback)

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

    async def _handle_deeplink_start(self, message: Message, uuid_str: str) -> None:
        """Handle Mini App deep link: /start q_<uuid>.

        Delegates to _process_miniapp_start with message for handle_query support.
        """
        await self._process_miniapp_start(
            chat_id=message.chat.id, uuid_str=uuid_str, message=message
        )

    async def _process_miniapp_start(
        self,
        chat_id: int,
        uuid_str: str,
        message: Message | None = None,
    ) -> None:
        """Process Mini App expert start request.

        Core logic shared by deep link handler and Redis pub/sub subscriber.
        When called from pub/sub (no message), RAG runs without streaming.
        """
        if self._deeplink_redis is None or self._topic_manager is None:
            logger.warning("Mini App start received but TopicManager not initialized")
            return

        key = f"miniapp:q:{uuid_str}"
        raw = await self._deeplink_redis.getdel(key)
        if raw is None:
            if message:
                await message.answer("Ссылка устарела. Пожалуйста, вернитесь в приложение.")
            else:
                logger.warning("Mini App payload expired: %s", uuid_str)
            return

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            if message:
                await message.answer("Ошибка обработки ссылки.")
            else:
                logger.error("Invalid Mini App payload: %s", uuid_str)
            return

        expert_id = payload.get("expert_id", "")
        user_message = payload.get("message") or ""

        from src.services.content_loader import load_mini_app_config

        config_data = load_mini_app_config()
        expert = next((e for e in config_data.get("experts", []) if e["id"] == expert_id), None)
        if not expert:
            if message:
                await message.answer("Эксперт не найден.")
            else:
                logger.warning("Expert not found: %s", expert_id)
            return

        # Note: answerWebAppQuery не поддерживает message_thread_id —
        # сообщение попало бы в General topic, дублируя контент в треде.
        # Поэтому пишем напрямую в forum topic через send_message.

        try:
            topic_id = await self._topic_manager.get_or_create_topic(
                chat_id=chat_id,
                expert_id=expert_id,
                expert_name=expert["name"],
                expert_emoji=expert.get("emoji", "💬"),
            )
        except TelegramBadRequest as exc:
            logger.error("Failed to create forum topic: %s", exc)
            if message:
                await message.answer("Не удалось создать тему. Попробуйте позже.")
            return

        if not user_message:
            return

        # Echo user question in the topic (retry on stale cache — deleted topic)
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic_id,
                text=f"❝ {user_message} ❞",
            )
        except TelegramBadRequest:
            logger.warning("Stale topic %d, invalidating and recreating", topic_id)
            await self._topic_manager.invalidate_topic(chat_id, expert_id)
            try:
                topic_id = await self._topic_manager.get_or_create_topic(
                    chat_id=chat_id,
                    expert_id=expert_id,
                    expert_name=expert["name"],
                    expert_emoji=expert.get("emoji", "💬"),
                )
                await self.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    text=f"❝ {user_message} ❞",
                )
            except TelegramBadRequest as exc2:
                logger.error("Failed to recreate topic: %s", exc2)
                return

        if message:
            # Deep link path: full handle_query with streaming support
            topic_msg = message.model_copy(
                update={"text": user_message, "message_thread_id": topic_id}
            )
            await self.handle_query(topic_msg)
        else:
            # Pub/sub path: direct RAG pipeline + send result
            await self._run_miniapp_rag(chat_id, topic_id, user_message)

    async def _run_miniapp_rag(self, chat_id: int, topic_id: int, user_message: str) -> None:
        """Run RAG pipeline for Mini App request (no aiogram Message available)."""
        try:
            from src.runtime.pipeline.rag import rag_pipeline
            from telegram_bot.services.generate_response import generate_response

            rag_result = await rag_pipeline(
                query=user_message,
                user_id=chat_id,
                session_id=f"miniapp:{chat_id}",
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
            )

            documents = rag_result.get("documents", [])
            if not documents:
                await self.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    text="К сожалению, я не нашёл информации по вашему запросу.",
                )
                return

            gen_result = await generate_response(
                query=user_message,
                documents=documents,
                config=self._graph_config,
            )
            answer = gen_result.get("response", "")
            if answer:
                await self.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    text=answer,
                )
        except Exception:
            logger.exception("RAG pipeline failed for miniapp (chat=%s)", chat_id)
            await self.bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic_id,
                text="Произошла ошибка при обработке запроса. Попробуйте ещё раз.",
            )

    async def _miniapp_subscriber_loop(self) -> None:
        """Subscribe to Redis miniapp:start channel and process requests.

        Redis-py handles transient reconnect/resubscribe through its SDK retry
        strategy; authentication errors remain permanent.
        """
        import redis.asyncio as aioredis
        from redis.backoff import ExponentialBackoff
        from redis.exceptions import AuthenticationError
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError
        from redis.retry import Retry

        pubsub = None
        sub_redis = None
        try:
            sub_redis = aioredis.from_url(
                self.config.redis_url,
                decode_responses=True,
                health_check_interval=30,
                retry=Retry(ExponentialBackoff(cap=60, base=1), 10),
                retry_on_error=[RedisConnectionError, RedisTimeoutError],
            )
            pubsub = sub_redis.pubsub()
            await pubsub.subscribe("miniapp:start")
            logger.info("Mini App pub/sub subscriber started")

            async for raw_msg in pubsub.listen():
                if raw_msg["type"] != "message":
                    continue
                try:
                    data = json.loads(raw_msg["data"])
                    uuid_str = data["uuid"]
                    user_id = int(data["user_id"])
                except (ValueError, TypeError, KeyError):
                    logger.warning("Invalid miniapp:start message: %s", raw_msg["data"])
                    continue

                logger.info("Mini App pub/sub: user=%s uuid=%s", user_id, uuid_str)
                await self._process_miniapp_start(chat_id=user_id, uuid_str=uuid_str)
        except asyncio.CancelledError:
            logger.info("Mini App pub/sub subscriber stopped")
            raise
        except AuthenticationError:
            logger.error("Mini App pub/sub: permanent Redis auth error, not retrying")
            raise
        except Exception:
            logger.exception("Mini App pub/sub subscriber crashed")
            raise
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe("miniapp:start")
                except Exception:
                    logger.debug(
                        "Failed to unsubscribe during cleanup",
                        exc_info=True,
                    )
            if sub_redis is not None:
                try:
                    await sub_redis.aclose()
                except Exception:
                    logger.debug(
                        "Failed to close Redis connection during cleanup",
                        exc_info=True,
                    )

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_ids

    @observe(name="menu-router", capture_input=False, capture_output=False)
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

        if dialog_manager is not None:
            from .dialogs.catalog import dispatch_catalog_text_action, is_catalog_state

            if is_catalog_state(current) and await dispatch_catalog_text_action(
                message=message,
                manager=dialog_manager,
                i18n_hub=getattr(self, "_i18n_hub", None),
            ):
                return

        handlers: dict[str, Any] = {
            "search": self._handle_search,
            "services": self._handle_services,
            "viewing": self._handle_viewing,
            "bookmarks": self._handle_bookmarks,
            "ask": self._handle_ask,
            "manager": self._handle_manager,
            "demo": self._handle_demo,
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
                await handler(
                    message,
                    i18n=i18n,
                    state=state,
                    dialog_manager=dialog_manager,
                )
            elif action_id == "demo":
                await handler(message)
            else:
                await handler(message)

    async def _handle_demo(self, message: Message) -> None:
        from .handlers.demo_handler import handle_demo_button

        await handle_demo_button(message)

    async def handle_menu_action_text(self, message: Message, query_text: str) -> None:
        """Dispatch text query to agent pipeline (from ReplyKeyboard context) (#628)."""
        patched = message.model_copy(update={"text": query_text})
        await self.handle_query(patched)

    @observe(name="menu-search", capture_input=False, capture_output=False)
    async def _handle_search(self, message: Message, dialog_manager: Any = None) -> None:
        return await _bot_catalog._handle_search(self, message, dialog_manager)

    @observe(name="menu-services", capture_input=False, capture_output=False)
    async def _handle_services(self, message: Message, i18n: Any = None) -> None:
        return await _bot_catalog._handle_services(self, message, i18n)

    @observe(name="menu-viewing", capture_input=False, capture_output=False)
    async def _handle_viewing(
        self, message: Message, state: FSMContext, dialog_manager: Any = None
    ) -> None:
        return await _bot_catalog._handle_viewing(self, message, state, dialog_manager)

    async def _send_property_card(
        self,
        message: Message,
        result: dict,
        telegram_id: int,
    ) -> Message:
        return await _bot_catalog._send_property_card(self, message, result, telegram_id)

    @observe(name="menu-bookmarks", capture_input=False, capture_output=False)
    async def _handle_bookmarks(self, message: Message, state: FSMContext | None = None) -> None:
        return await _bot_favorites._handle_bookmarks(self, message, state)

    # Mapping callback_data -> query text for RAG pipeline
    _ASK_QUERIES: dict[str, str] = {
        "ask:docs": "Какие документы нужны для покупки?",
        "ask:costs": "Сколько стоит оформление сделки?",
        "ask:vnzh": "Как получить ВНЖ в Болгарии?",
        "ask:installment": "Какие условия рассрочки?",
    }

    @observe(name="menu-ask", capture_input=False, capture_output=False)
    async def _handle_ask(self, message: Message, i18n: Any = None) -> None:
        return await _bot_catalog._handle_ask(self, message, i18n)

    @observe(name="cb-ask", capture_input=False, capture_output=False)
    async def handle_ask_callback(self, callback: CallbackQuery) -> None:
        return await _bot_catalog.handle_ask_callback(self, callback)

    @observe(name="menu-manager", capture_input=False, capture_output=False)
    async def _handle_manager(
        self,
        message: Message,
        i18n: Any = None,
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_handoff._handle_manager(self, message, i18n, state, dialog_manager)

    async def _handle_group_message(self, message: Message) -> None:
        return await _bot_handoff._handle_group_message(self, message)

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
        return await _bot_handoff._complete_handoff(
            self, user_id, username, display_name, locale, qualification, message, state
        )

    async def _close_handoff(self, handoff: HandoffData) -> None:
        return await _bot_handoff._close_handoff(self, handoff)

    @observe(name="cb-service", capture_input=False, capture_output=False)
    async def handle_service_callback(self, callback: CallbackQuery, i18n: Any = None) -> None:
        return await _bot_catalog.handle_service_callback(self, callback, i18n)

    @observe(name="cb-cta", capture_input=False, capture_output=False)
    async def handle_cta_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_catalog.handle_cta_callback(self, callback, state, dialog_manager)

    async def handle_fav_add(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_favorites.handle_fav_add(
            self, callback, state, callback_data, dialog_manager
        )

    async def handle_fav_remove(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_favorites.handle_fav_remove(
            self, callback, state, callback_data, dialog_manager
        )

    async def handle_fav_viewing(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_favorites.handle_fav_viewing(
            self, callback, state, callback_data, dialog_manager
        )

    async def handle_fav_viewing_all(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_favorites.handle_fav_viewing_all(
            self, callback, state, callback_data, dialog_manager
        )

    @observe(name="cb-favorite", capture_input=False, capture_output=False)
    async def handle_favorite_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_favorites.handle_favorite_callback(
            self, callback, state, callback_data, dialog_manager
        )

    @observe(name="cb-results", capture_input=False, capture_output=False)
    async def handle_results_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: ResultsCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_catalog.handle_results_callback(
            self, callback, state, callback_data, dialog_manager
        )

    @observe(name="cb-card", capture_input=False, capture_output=False)
    async def handle_card_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_catalog.handle_card_callback(self, callback, state, dialog_manager)

    @observe(name="telegram-rag-query", capture_input=False, capture_output=False)
    async def handle_query(
        self,
        message: Message,
        locale: str = "ru",
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ):
        return await _bot_query_pipeline.handle_query(self, message, locale, state, dialog_manager)

    async def _send_markdown_chunks(
        self,
        message: Message,
        text: str,
        *,
        reply_markup: Any | None = None,
    ) -> None:
        """Send long Telegram response in chunks with Telegram HTML formatting."""
        from telegram_bot.services.telegram_formatting import send_html_messages

        await send_html_messages(message, text, reply_markup=reply_markup)

    async def _handle_apartment_fast_path(
        self,
        *,
        user_text: str,
        message: Message,
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ) -> str | None:
        return await _bot_query_pipeline._handle_apartment_fast_path(
            self, user_text=user_text, message=message, state=state, dialog_manager=dialog_manager
        )

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
        dialog_manager: Any = None,
    ) -> str | None:
        return await _bot_query_pipeline._handle_client_direct_pipeline(
            self,
            message=message,
            user_text=user_text,
            user_id=user_id,
            session_id=session_id,
            role=role,
            query_type=query_type,
            rag_result_store=rag_result_store,
            state=state,
            dialog_manager=dialog_manager,
        )

    @staticmethod
    def _trace_guard_blocked(
        *,
        user_text: str,
        query_type: str,
        pipeline_start: float,
        risk_score: float,
        pattern: str | None,
        root_trace_metadata: dict[str, Any] | None,
    ) -> None:
        return _bot_query_pipeline._trace_guard_blocked(
            user_text=user_text,
            query_type=query_type,
            pipeline_start=pipeline_start,
            risk_score=risk_score,
            pattern=pattern,
            root_trace_metadata=root_trace_metadata,
        )

    async def _handle_pre_agent_cache_hit(
        self,
        *,
        message: Any,
        cached: str,
        user_text: str,
        query_type: str,
        role: str,
        pipeline_start: float,
        pre_agent_start: float,
        rag_result_store: dict[str, Any],
        root_trace_metadata: dict[str, Any] | None,
        dense: list[float],
    ) -> str:
        return await _bot_query_pipeline._handle_pre_agent_cache_hit(
            self,
            message=message,
            cached=cached,
            user_text=user_text,
            query_type=query_type,
            role=role,
            pipeline_start=pipeline_start,
            pre_agent_start=pre_agent_start,
            rag_result_store=rag_result_store,
            root_trace_metadata=root_trace_metadata,
            dense=dense,
        )

    async def _send_core_response(
        self,
        *,
        message: Any,
        response_text: str,
        user_text: str,
        query_type: str,
        rag_result_store: dict[str, Any],
        ctx: Any,
        forum_thread_id: int | None,
    ) -> None:
        return await _bot_query_pipeline._send_core_response(
            self,
            message=message,
            response_text=response_text,
            user_text=user_text,
            query_type=query_type,
            rag_result_store=rag_result_store,
            ctx=ctx,
            forum_thread_id=forum_thread_id,
        )

    @staticmethod
    def _write_final_pipeline_trace(
        *,
        user_text: str,
        wall_ms: float,
        pre_agent_ms: float,
        filter_signature: str | None,
        rag_result_store: dict[str, Any],
        root_trace_metadata: dict[str, Any] | None,
    ) -> None:
        return _bot_query_pipeline._write_final_pipeline_trace(
            user_text=user_text,
            wall_ms=wall_ms,
            pre_agent_ms=pre_agent_ms,
            filter_signature=filter_signature,
            rag_result_store=rag_result_store,
            root_trace_metadata=root_trace_metadata,
        )

    @observe(
        name="telegram-rag-supervisor",
        capture_input=False,
        capture_output=False,
    )
    async def _handle_query_supervisor(
        self,
        message: Message,
        pipeline_start: float,
        locale: str = "ru",
        root_trace_metadata: dict[str, Any] | None = None,
        state: FSMContext | None = None,
        forum_thread_id: int | None = None,
        expert_id: str | None = None,
        dialog_manager: Any = None,
    ) -> str:
        return await _bot_query_pipeline._handle_query_supervisor(
            self,
            message,
            pipeline_start,
            locale,
            root_trace_metadata,
            state,
            forum_thread_id,
            expert_id,
            dialog_manager,
        )

    @observe(
        name="telegram-rag-agent-stream",
        capture_input=False,
        capture_output=False,
        as_type="agent",
    )
    async def _astream_supervisor_with_recovery(
        self,
        *,
        agent: Any,
        tools: list[Any],
        role: str,
        user_text: str,
        chat_id: int,
        callbacks: list[Any],
        bot_context: BotContextType,
        rag_result_store: dict[str, Any],
        forum_thread_id: int | None = None,
        use_streaming: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        return await _bot_query_pipeline._astream_supervisor_with_recovery(
            self,
            agent=agent,
            tools=tools,
            role=role,
            user_text=user_text,
            chat_id=chat_id,
            callbacks=callbacks,
            bot_context=bot_context,
            rag_result_store=rag_result_store,
            forum_thread_id=forum_thread_id,
            use_streaming=use_streaming,
        )

    @observe(
        name="telegram-rag-agent-invoke",
        capture_input=False,
        capture_output=False,
        as_type="agent",
    )
    async def _ainvoke_supervisor_with_recovery(
        self,
        *,
        agent: Any,
        tools: list[Any],
        role: str,
        user_text: str,
        chat_id: int,
        callbacks: list[Any],
        bot_context: BotContextType,
        rag_result_store: dict[str, Any],
        forum_thread_id: int | None = None,
        message: Any | None = None,
    ) -> dict[str, Any]:
        return await _bot_query_pipeline._ainvoke_supervisor_with_recovery(
            self,
            agent=agent,
            tools=tools,
            role=role,
            user_text=user_text,
            chat_id=chat_id,
            callbacks=callbacks,
            bot_context=bot_context,
            rag_result_store=rag_result_store,
            forum_thread_id=forum_thread_id,
            message=message,
        )

    @observe(name="telegram-rag-voice")
    async def handle_voice(self, message: Message):
        """Handle voice message via Whisper STT + imperative RAG pipeline."""
        from src.runtime.graph.state import make_initial_state

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
                    # Direct checkpoint overhead measurement (#1258): the
                    # checkpointer wrapper accumulates per-method I/O times
                    # into a ContextVar bucket while this capture is active.
                    # Falls back to the proxy when the checkpointer is not
                    # instrumented (e.g. MemorySaver in tests).
                    overhead_bucket: dict[str, float] | None = begin_checkpoint_overhead_capture()
                    try:
                        result = await graph.ainvoke(state, config=invoke_config)
                    finally:
                        overhead_bucket = end_checkpoint_overhead_capture()
                    ainvoke_wall_ms = (time.perf_counter() - invoke_start) * 1000
                    if overhead_bucket and overhead_bucket.get("calls", 0):
                        result["checkpointer_overhead_ms"] = sum_checkpoint_overhead_ms(
                            overhead_bucket
                        )
                        result["checkpointer_op_count"] = int(overhead_bucket.get("calls", 0))
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
            except GraphRecursionError:
                logger.warning(
                    "Voice pipeline recursion limit exceeded (user=%s, session=%s)",
                    state.get("user_id"),
                    state.get("session_id"),
                    exc_info=True,
                )
                await message.answer(
                    "Запрос слишком сложный — достигнут лимит обработки. "
                    "Попробуйте упростить его или отправить текстом."
                )
                try:
                    _write_voice_error_scores(
                        get_client(),
                        trace_id=state.get("trace_id", ""),
                        voice_duration_s=voice.duration,
                        error_reason="recursion_limit",
                    )
                except Exception:
                    logger.debug("Failed to write voice error scores", exc_info=True)
                return
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
                lf.update_current_span(
                    input=build_safe_input_payload(
                        content_type="voice",
                        text=result.get("stt_text", ""),
                        extra={"voice_duration_s": voice.duration},
                    ),
                    output=build_safe_output_payload(
                        answer_text=result.get("response", ""),
                        chunks_count=1,
                        sources_count=result.get("sources_count")
                        or result.get("search_results_count", 0),
                    ),
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

    async def _send_hitl_confirmation(
        self,
        message: Message,
        payload: dict,
        thread_id: str,
    ) -> None:
        """Send inline keyboard for HITL confirmation (#443)."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        from .agents.hitl import set_pending_resume_trace_id

        # #2224: remember the trace that raised this interrupt so the later
        # Command(resume=...) trace can back-link to it via resumes_trace_id.
        with contextlib.suppress(Exception):
            set_pending_resume_trace_id(thread_id, get_client().get_current_trace_id())

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

    @observe(name="telegram-hitl-callback", as_type="agent")
    async def handle_hitl_callback(self, callback: CallbackQuery) -> None:
        """Handle HITL approve/cancel button click (#443)."""
        from .agents.context import BotContext

        if callback.from_user is None or callback.message is None:
            await callback.answer()
            return

        data = callback.data or ""
        action = "approve" if data == "hitl:approve" else "cancel"
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id
        _raw_thread_id = getattr(callback.message, "message_thread_id", None)
        forum_thread_id: int | None = _raw_thread_id if isinstance(_raw_thread_id, int) else None
        thread_id = _supervisor_thread_id(chat_id, forum_thread_id)

        # #2224: link this resume trace back to the interrupt trace stored at
        # confirmation time. Langfuse trace metadata values are strings.
        from .agents.hitl import pop_pending_resume_trace_id

        _parent_trace_id = pop_pending_resume_trace_id(thread_id)
        _resume_trace_metadata = (
            {"resumes_trace_id": _parent_trace_id} if _parent_trace_id else None
        )

        await callback.answer("Принято" if action == "approve" else "Отменено")

        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]

        # Rebuild agent with same tools and checkpointer (mirrors _handle_query_supervisor)
        from .agents.tool_assembly import build_agent_tools

        role = await self._resolve_user_role(user_id)
        session_id = make_session_id("chat", chat_id)

        tools = build_agent_tools(
            role=role,
            config=self.config,
            history_service=self._history_service,
        )

        agent = create_bot_agent(
            model=self.config.supervisor_model,
            tools=tools,
            checkpointer=self._agent_checkpointer,
            language=self.config.domain_language,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            role=role,
            max_history_messages=self.config.agent_max_history_messages,
            max_tokens=self.config.supervisor_max_tokens,
        )

        ctx = BotContext(
            telegram_user_id=user_id,
            session_id=session_id,
            language=self.config.domain_language,
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
            apartments_service=self._apartments_service,
            search_event_store=self._search_event_store,
            config=self.config,
        )

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "hitl", "resume"],
            metadata=_resume_trace_metadata,
        ):
            langfuse_handler = create_callback_handler()
            callbacks = [langfuse_handler] if langfuse_handler else []

            result = await agent.ainvoke(
                {"resume": {"action": action}},
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
            bot = callback.message.bot  # type: ignore[union-attr]
            for chunk in _split_telegram_response(response_text):
                send_kwargs: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
                if forum_thread_id is not None:
                    send_kwargs["message_thread_id"] = forum_thread_id
                await bot.send_message(**send_kwargs)  # type: ignore[union-attr]

        lf = get_client()
        lf.score_current_trace(name="hitl_action", value=action, data_type="CATEGORICAL")

    @observe(name="cb-feedback", capture_input=False, capture_output=False)
    async def handle_feedback(
        self, callback: CallbackQuery, callback_data: FeedbackCB | None = None
    ) -> None:
        """Thin wrapper — see ``_bot_feedback_handlers`` (#2048 PR-9a)."""
        await _bot_feedback_handlers.handle_feedback(self, callback, callback_data)

    @observe(name="cb-feedback-reason", capture_input=False, capture_output=False)
    async def handle_feedback_reason(
        self, callback: CallbackQuery, callback_data: FeedbackReasonCB
    ) -> None:
        """Thin wrapper — see ``_bot_feedback_handlers`` (#2048 PR-9a)."""
        await _bot_feedback_handlers.handle_feedback_reason(self, callback, callback_data)

    async def _clear_feedback_confirmation_later(
        self, message: Any, delay_s: float = _FEEDBACK_CONFIRMATION_TTL_S
    ) -> None:
        """Thin wrapper — see ``_bot_feedback_handlers`` (#2048 PR-9a)."""
        await _bot_feedback_handlers.clear_feedback_confirmation_later(message, delay_s)

    @observe(name="cb-clearcache", capture_input=False, capture_output=False)
    async def handle_clearcache_callback(self, callback_query: CallbackQuery) -> None:
        """Handle /clearcache inline keyboard callbacks (cc: prefix)."""
        _TIER_NAMES = {
            "semantic": "Semantic cache",
            "embeddings": "Embeddings cache",
            "sparse": "Sparse embeddings cache",
            "search": "Search + Rerank cache",
            "rerank": "Rerank cache",
            "all": "Все кеши",
            "history": "История диалога",
            "all_and_history": "Все кеши + История диалога",
        }
        data = (callback_query.data or "").removeprefix("cc:")
        tier_name = _TIER_NAMES.get(data, data)
        try:
            if data in ("history", "all_and_history"):
                # Clear agent conversation history (checkpoints) for this user
                from telegram_bot.services.checkpointer_utils import (
                    _delete_checkpointer_thread,
                    _supervisor_thread_id,
                )

                assert callback_query.from_user is not None
                user_id = callback_query.from_user.id
                chat_id = callback_query.message.chat.id if callback_query.message else user_id
                text_thread_id = _supervisor_thread_id(chat_id)
                voice_thread_id = str(user_id)
                seen: set[int] = set()
                for checkpointer in (self._checkpointer, self._agent_checkpointer):
                    if checkpointer is None or id(checkpointer) in seen:
                        continue
                    seen.add(id(checkpointer))
                    for thread_id in (text_thread_id, voice_thread_id):
                        try:
                            await _delete_checkpointer_thread(checkpointer, thread_id)
                        except Exception:
                            logger.warning(
                                "Failed to clear checkpointer thread %s", thread_id, exc_info=True
                            )
                if data == "history":
                    text = "Очищено: История диалога"
                else:
                    # Also clear all caches
                    result = await self._cache.clear_all_caches()
                    lines = [
                        f"Очищено: {_TIER_NAMES.get(t, t)} — {n} ключей" for t, n in result.items()
                    ]
                    lines.append("Очищено: История диалога")
                    text = "\n".join(lines)
            elif data == "all":
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
            await callback_query.message.edit_text(text)  # type: ignore[union-attr]

    async def handle_menu_action(
        self, callback: CallbackQuery, query_text: str, locale: str = "ru"
    ) -> None:
        """Handle menu button click — dispatch query_text to agent pipeline.

        Called by on_click handlers in dialog files after manager.done().
        Reuses _ainvoke_supervisor_with_recovery for consistency with handle_query.
        """
        from .agents.agent import LOCALE_TO_LANGUAGE
        from .agents.context import BotContext

        if callback.from_user is None or callback.message is None:
            return

        user_id = callback.from_user.id
        chat_id = callback.message.chat.id
        bot = callback.message.bot

        role = await self._resolve_user_role(user_id)
        language = LOCALE_TO_LANGUAGE.get(locale, self.config.domain_language)
        session_id = make_session_id("chat", chat_id)

        # Build tools list via shared helper
        from .agents.tool_assembly import build_agent_tools

        tools = build_agent_tools(
            role=role,
            config=self.config,
            history_service=self._history_service,
        )

        agent = create_bot_agent(
            model=self.config.supervisor_model,
            tools=tools,
            checkpointer=self._agent_checkpointer,
            language=language,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            role=role,
            max_history_messages=self.config.agent_max_history_messages,
            max_tokens=self.config.supervisor_max_tokens,
        )

        ctx = BotContext(
            telegram_user_id=user_id,
            session_id=session_id,
            language=language,
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
            original_query=query_text,
            original_user_query=query_text,
            bot=bot,
            manager_ids=list(self.config.manager_ids),
            apartments_service=self._apartments_service,
            search_event_store=self._search_event_store,
            config=self.config,
        )

        rag_result_store: dict[str, Any] = {}

        with propagate_attributes(
            session_id=session_id,
            user_id=str(user_id),
            tags=["telegram", "menu", "agent"],
        ):
            langfuse_handler = create_callback_handler()
            callbacks = [langfuse_handler] if langfuse_handler else []
            async with ChatActionSender.typing(bot=bot, chat_id=chat_id):  # type: ignore[arg-type]
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
        startup_report = StartupReport()

        # Authoritative dependency gate must run before Redis-backed startup work.
        from .preflight import PreflightError, check_dependencies

        try:
            preflight_result = await check_dependencies(self.config, log_summary=False)
        except PreflightError as exc:
            startup_report.merge(exc.report)
            logger.error(startup_report.render())
            raise
        preflight_report = getattr(preflight_result, "report", None)
        if isinstance(preflight_report, StartupReport):
            startup_report.merge(preflight_report)

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
            startup_report.add(
                StartupSignal(
                    source="conversation_memory",
                    severity=StartupSeverity.DEGRADED,
                    summary="Redis checkpointer unavailable, using in-memory fallback",
                    remediation="restore Redis connectivity for persistent conversation memory",
                )
            )

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
            startup_report.add(
                StartupSignal(
                    source="agent_memory",
                    severity=StartupSeverity.DEGRADED,
                    summary="Agent Redis checkpointer unavailable, using in-memory fallback",
                    remediation="restore Redis connectivity for persistent agent state",
                )
            )

        # Initialize TopicManager + deeplink Redis for Mini App deep link flow
        if self.config.expert_topics_enabled:
            import redis.asyncio as aioredis

            from telegram_bot.services.topic_manager import TopicManager

            self._deeplink_redis = aioredis.from_url(self.config.redis_url, decode_responses=True)
            self._topic_manager: TopicManager | None = TopicManager(
                bot=self.bot, redis=self._deeplink_redis
            )
            logger.info("TopicManager ready (expert deep link flow)")
        else:
            self._deeplink_redis = None
            self._topic_manager = None
        self._miniapp_subscriber_task: asyncio.Task[None] | None = None
        # Initialize history service (Qdrant-backed Q&A history)
        try:
            history_service_cls = HistoryService
            if history_service_cls is None:
                from .services.history_service import HistoryService as history_service_cls

            # REST-only client for collection admin ops: the shared retrieval
            # client is prefer_grpc=True, and gRPC collection calls hit a
            # grpc.aio + OTel interceptor NotImplementedError (#2346).
            from urllib.parse import urlparse

            # Strip api_key for http:// to avoid insecure-connection warning (#570).
            async_qdrant_client_cls = AsyncQdrantClient
            if async_qdrant_client_cls is None:
                from qdrant_client import AsyncQdrantClient as async_qdrant_client_cls

            _hist_scheme = urlparse(self.config.qdrant_url).scheme.lower()
            _hist_api_key = self.config.qdrant_api_key if _hist_scheme == "https" else None
            self._history_rest_client = async_qdrant_client_cls(
                url=self.config.qdrant_url,
                api_key=_hist_api_key,
                timeout=self.config.qdrant_timeout,
                prefer_grpc=False,
            )
            self._history_service = history_service_cls(
                client=self._qdrant.client,
                embeddings=self._embeddings,
                collection_name=self.config.qdrant_history_collection,
                rest_client=self._history_rest_client,
            )
            await self._history_service.ensure_collection()
            logger.info("History service ready (%s)", self.config.qdrant_history_collection)
        except Exception:
            logger.warning("History service init failed, /history disabled", exc_info=True)
            self._history_service = None
            startup_report.add(
                StartupSignal(
                    source="history",
                    severity=StartupSeverity.DEGRADED,
                    summary="/history disabled because history service initialization failed",
                    remediation="restore Qdrant history collection and embeddings dependencies",
                )
            )

        # Initialize PostgreSQL pool for realestate DB
        postgres_available = (
            preflight_result.get("postgres", True) if isinstance(preflight_result, dict) else True
        )
        if postgres_available:
            try:
                import asyncpg

                test_conn: Any | None = None
                try:
                    # Validate DB exists before creating pool (avoid traceback spam #570)
                    test_conn = await asyncpg.connect(
                        self.config.realestate_database_url, timeout=5
                    )
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
                    test_conn = await asyncpg.connect(
                        self.config.realestate_database_url, timeout=5
                    )
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

                # Initialize favorites service (#628)
                from .services.favorites_service import FavoritesService

                self._favorites_service = FavoritesService(pool=self._pg_pool)
                logger.info("Favorites service ready")

                from .services.search_event_store import SearchEventStore

                self._search_event_store = SearchEventStore(pool=self._pg_pool)
                logger.info("Search event store ready")

            except Exception:
                logger.warning("PostgreSQL pool init failed, user features disabled", exc_info=True)
                startup_report.add(
                    StartupSignal(
                        source="postgres_runtime",
                        severity=StartupSeverity.DEGRADED,
                        summary="PostgreSQL pool unavailable, user features disabled",
                        remediation=(
                            "restore PostgreSQL connectivity for favorites, search events, "
                            "and user services"
                        ),
                    )
                )
        else:
            startup_report.add(
                StartupSignal(
                    source="postgres_runtime",
                    severity=StartupSeverity.DEGRADED,
                    summary="PostgreSQL unavailable — preflight marked it as not reachable",
                    remediation=(
                        "restore PostgreSQL connectivity for favorites, search events, "
                        "and user services"
                    ),
                )
            )
            logger.info(
                "Skipping PostgreSQL pool init because preflight already marked it unavailable"
            )

        # Cache bot user id for echo-skip in group handlers (#730 review)
        try:
            me = await self.bot.me()
            self._bot_user_id = me.id
        except Exception:
            logger.warning("Failed to cache bot user id")

        # Verify forum topics mode is enabled for expert threads
        try:
            me = await self.bot.get_me()
            if not getattr(me, "has_topics_enabled", False):
                logger.warning(
                    "Forum topics not enabled for this bot. "
                    "Enable 'Topics in Private Chats' via BotFather Mini App. "
                    "Thread routing will be disabled."
                )
                self._topics_enabled = False
            else:
                self._topics_enabled = True
                logger.info("Forum topics mode: enabled")
        except Exception:
            logger.warning("Failed to check forum topics status", exc_info=True)
            self._topics_enabled = False

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

        # Register services in dp.workflow_data so all handlers receive them via data dict
        self.dp["user_service"] = self._user_service
        self.dp["pg_pool"] = self._pg_pool
        self.dp["bot_config"] = self.config
        self.dp["property_bot"] = self
        self.dp["apartments_service"] = self._apartments_service
        self.dp["favorites_service"] = self._favorites_service
        self.dp["search_event_store"] = self._search_event_store
        self.dp["pipeline"] = self._apartment_pipeline
        self.dp["embeddings"] = self._hybrid
        self.dp["llm"] = self._llm

        if self._i18n_hub is None:
            self._i18n_hub = create_translator_hub()
        setup_i18n_middleware(self.dp, self._i18n_hub, self._user_service)
        logger.info("i18n middleware ready")

        # Setup aiogram-dialog routers, including the client root shell.
        from aiogram_dialog import setup_dialogs as aiogram_setup_dialogs

        from .dialogs.catalog import catalog_dialog
        from .dialogs.client_menu import client_menu_dialog
        from .dialogs.demo import demo_dialog
        from .dialogs.faq import faq_dialog
        from .dialogs.filter_dialog import filter_dialog
        from .dialogs.funnel import funnel_dialog
        from .dialogs.handoff import handoff_dialog
        from .dialogs.settings import settings_dialog
        from .dialogs.viewing import viewing_dialog

        self.dp.include_router(client_menu_dialog)
        self.dp.include_router(catalog_dialog)
        self.dp.include_router(settings_dialog)
        self.dp.include_router(demo_dialog)
        self.dp.include_router(funnel_dialog)
        self.dp.include_router(filter_dialog)
        self.dp.include_router(faq_dialog)
        self.dp.include_router(viewing_dialog)
        self.dp.include_router(handoff_dialog)

        # Catch-all text handler — AFTER all dialog routers so that dialog
        # MessageInput (e.g. viewing phone input) is resolved first.
        # aiogram SDK: handlers match in registration order, first-match wins.
        from aiogram import Router as _Router

        self._catch_all_router = _Router(name="catch_all_query")
        self._catch_all_router.message(
            StateFilter(None),
            F.text,
            flags={"rate_limit": {"rate": 2.0, "key": "query"}},
        )(self.handle_query)
        self.dp.include_router(self._catch_all_router)

        aiogram_setup_dialogs(self.dp)
        logger.info("aiogram-dialog setup complete")

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
                BotCommand(command="metrics", description="Метрики пайплайна в JSON logs"),
                BotCommand(command="clearcache", description="Очистить кеш Redis"),
            ]
        )

        # Set Menu Button: WebApp when MINI_APP_URL is configured, else commands list (#883)
        if self.config.mini_app_url:
            from aiogram.types import MenuButtonWebApp, WebAppInfo

            await self.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Открыть",
                    web_app=WebAppInfo(url=self.config.mini_app_url),
                )
            )
            logger.info("Mini App menu button set: %s", self.config.mini_app_url)
        else:
            from aiogram.types import MenuButtonCommands

            await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

        # Warm up BGE-M3 connection pool (#953)
        await self._warmup_bge()

        # Start Mini App pub/sub subscriber (Redis → bot, bypasses openTelegramLink bug)
        if self._topic_manager is not None:
            self._miniapp_subscriber_task = asyncio.create_task(
                self._miniapp_subscriber_loop(), name="miniapp-pubsub"
            )

        if startup_report.final_severity is StartupSeverity.FAILED:
            logger.error(startup_report.render())
        elif startup_report.final_severity is StartupSeverity.DEGRADED:
            logger.warning(startup_report.render())
        else:
            logger.info(startup_report.render())

        if self._cache.redis is not None:
            self._polling_lock = RedisPollingLock(
                redis=self._cache.redis,
                key=POLLING_LOCK_KEY,
            )
            self._polling_lock_owner = f"{socket.gethostname()}:{os.getpid()}"
            await self._polling_lock.acquire(self._polling_lock_owner)
            refresh_interval = max(1, self._polling_lock.ttl_sec // 3)
            self._polling_lock_consecutive_failures = 0

            async def _polling_lock_heartbeat_loop() -> None:
                while True:
                    await asyncio.sleep(refresh_interval)
                    try:
                        await self._polling_lock_heartbeat_tick()
                    except Exception:
                        logger.exception("Polling lock heartbeat loop error")

            self._polling_lock_task = asyncio.create_task(
                _polling_lock_heartbeat_loop(), name="polling-lock-heartbeat"
            )

        # DEPS-OBS3: in-process Prometheus /metrics is removed. Pipeline
        # counters/latencies are emitted as structured JSON product logs.

        try:
            await self.dp.start_polling(self.bot)
        finally:
            if self._polling_lock_task is not None:
                self._polling_lock_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._polling_lock_task
                self._polling_lock_task = None

    async def _warmup_bge(self) -> None:
        """Warm up BGE-M3 connection pool (#953).

        Thin delegate to :func:`telegram_bot._bot_lifecycle.warmup_bge_pool`
        — see ``docs/engineering/bot-decomposition-plan-2026-05-27.md``
        (#1265 / #2048 PR-8).
        """
        await _bot_lifecycle.warmup_bge_pool(self._hybrid, log=logger)

    async def _polling_lock_heartbeat_tick(self) -> None:
        """Single heartbeat tick: refresh the Redis polling lock.

        Thin delegate to
        :func:`telegram_bot._bot_lifecycle.polling_lock_heartbeat_tick` —
        see ``docs/engineering/bot-decomposition-plan-2026-05-27.md``
        (#1265 / #2048 PR-8).
        """
        await _bot_lifecycle.polling_lock_heartbeat_tick(
            self,
            log=logger,
            max_refresh_failures=_POLLING_LOCK_MAX_REFRESH_FAILURES,
        )

    async def stop(self):
        """Stop bot and cleanup."""
        logger.info("Stopping bot...")

        # Drain pending fire-and-forget history saves before tearing services down
        # so in-flight DB writes are not lost on shutdown (#1600). Bounded by
        # _history_save_drain_timeout_s so a stuck DB cannot block shutdown.
        if self._history_save_tasks:
            in_flight = list(self._history_save_tasks)
            logger.info("Draining %d in-flight history-save tasks...", len(in_flight))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*in_flight, return_exceptions=True),
                    timeout=self._history_save_drain_timeout_s,
                )
            except TimeoutError:
                logger.warning(
                    "history-save drain timed out after %.1fs; cancelling %d task(s)",
                    self._history_save_drain_timeout_s,
                    sum(1 for t in in_flight if not t.done()),
                )
                for task in in_flight:
                    if not task.done():
                        task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.gather(*in_flight, return_exceptions=True)
        if self._miniapp_subscriber_task is not None:
            self._miniapp_subscriber_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._miniapp_subscriber_task
            self._miniapp_subscriber_task = None
        if self._polling_lock_task is not None:
            self._polling_lock_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._polling_lock_task
            self._polling_lock_task = None
        if self._polling_lock is not None and self._polling_lock_owner is not None:
            try:
                await self._polling_lock.release()
            except Exception:
                logger.warning("Failed to release polling lock cleanly", exc_info=True)
            finally:
                self._polling_lock = None
                self._polling_lock_owner = None
        await self._redis_monitor.stop()
        await self._cache.close()
        await self._qdrant.close()
        if self._history_rest_client is not None:
            with contextlib.suppress(Exception):
                await self._history_rest_client.close()
            self._history_rest_client = None
        if hasattr(self._embeddings, "aclose"):
            await self._embeddings.aclose()
        if hasattr(self._sparse, "aclose"):
            await self._sparse.aclose()
        if self._reranker and hasattr(self._reranker, "close"):
            await self._reranker.close()
        self._pre_agent_filter_extractor = None
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
        if self._pg_pool is not None:
            await self._pg_pool.close()
            logger.info("PostgreSQL pool closed")
        if self._deeplink_redis is not None:
            await self._deeplink_redis.aclose()
            self._deeplink_redis = None
        await self.bot.session.close()
