"""Main Telegram bot logic — PropertyBot thin orchestrator.

Module-level helpers are extracted to focused ``_bot_*`` submodules and
lifecycle/observability subpackages.
The thin wrappers below preserve the ``from telegram_bot.bot import X``
import surface for tests that ``patch("telegram_bot.bot.X", ...)``.

Extraction map:
  observability/state_helpers (card_2a71ec058138, #1265 PR-1),
  observability/bot_observability (card_2a71ec058138, #1265 PR-2),
  handlers/error_classification (#1265 PR-3),
  pipeline/streaming (#1265 PR-4, card_2a71ec058138 SLICE 3),
  pipeline/pre_agent (#1265 PR-5, card_2a71ec058138 SLICE 3),
  pipeline/supervisor (#2816 Slice 2, card_2a71ec058138 SLICE 3),
  lifecycle/lifecycle (card_2a71ec058138),
  handlers/{catalog,favorites,bot_handoff,bot_crm_callbacks,feedback_handlers} (card_2a71ec058138 SLICE 2),
  handlers/command_handlers (card_c6ade99aada1).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
)

from src.runtime.integrations.polling_lock import RedisPollingLock
from src.services.handoff_state import HandoffData, HandoffState

from .callback_data import FavoriteCB, FeedbackCB, FeedbackReasonCB, ResultsCB
from .config import BotConfig
from .handlers import (
    bot_crm_callbacks as _bot_crm_callbacks,  # #2980: extracted clearcache callback handler
)
from .handlers import (
    bot_handoff as _bot_handoff,  # #2816 Slice 2: extracted handoff handlers
)
from .handlers import (
    catalog as _bot_catalog,  # #2816 Slice 2: extracted catalog/card handlers
)
from .handlers import (
    error_classification as _bot_error_classification,  # #1265 Slice 1 PR-3: extracted error-classification helpers
)
from .handlers import (
    favorites as _bot_favorites,  # #2816 Slice 2: extracted favorites handlers
)
from .handlers import (
    feedback_handlers as _bot_feedback_handlers,  # #2048 PR-9a: extracted feedback callback handlers
)
from .lifecycle import lifecycle as _bot_lifecycle  # card_2a71ec058138: homed to lifecycle/
from .middlewares import setup_error_handler, setup_throttling_middleware
from .middlewares.fsm_cancel import FSMCancelMiddleware
from .observability import (
    bot_observability as _bot_observability,  # card_2a71ec058138: homed to observability/
)
from .observability import (
    state_helpers as _bot_state_helpers,  # card_2a71ec058138: homed to observability/
)
from .pipeline import pre_agent as _bot_pre_agent  # card_2a71ec058138 SLICE 3: moved to pipeline/
from .pipeline import streaming as _bot_streaming  # card_2a71ec058138 SLICE 3: moved to pipeline/
from .pipeline import (
    supervisor as _bot_query_pipeline,  # card_2a71ec058138 SLICE 3: moved to pipeline/
)
from .services.forum_bridge import ForumBridge


class GraphRecursionError(RuntimeError):
    """Compatibility exception after legacy graph removal."""


if TYPE_CHECKING:
    from .agents.context import BotContext as BotContextType
    from .lifecycle.services import Services  # card_2a71ec058138: homed to lifecycle/
else:
    BotContextType = Any
    Services = Any

# Keep a patchable module-level symbol for tests without importing qdrant-heavy code.
AsyncQdrantClient: Any = None
BotContext: Any = Any


logger = logging.getLogger(__name__)

# --- Checkpoint namespace constants (versioned for safe migration) ---
_FEEDBACK_CONFIRMATION_TTL_S = 5.0
_APARTMENT_PAGE_SIZE = 5
_NO_RAG_QUERY_TYPES: frozenset[str] = frozenset({"CHITCHAT", "OFF_TOPIC"})
# Heartbeat runs every ttl/3, so a third consecutive miss can consume the full lease.
_POLLING_LOCK_MAX_REFRESH_FAILURES = 2


def create_bot_agent(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from .agents.agent import create_bot_agent as _create_bot_agent

    return _create_bot_agent(*args, **kwargs)


def classify_query(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from src.runtime.routing.classify import classify_query as _classify_query

    return _classify_query(*args, **kwargs)


def detect_injection(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper that keeps module-level patchability for tests."""
    from src.runtime.safety.guard import detect_injection as _detect_injection

    return _detect_injection(*args, **kwargs)


def _build_pre_agent_state_contract(*args: Any, **kwargs: Any) -> Any:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    return _bot_pre_agent._build_pre_agent_state_contract(*args, **kwargs)


def _has_async_method(obj: Any, name: str) -> bool:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    return _bot_pre_agent._has_async_method(obj, name)


async def _get_or_compute_pre_agent_dense(*args: Any, **kwargs: Any) -> Any:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    return await _bot_pre_agent._get_or_compute_pre_agent_dense(*args, **kwargs)


async def _prepare_pre_agent_retrieval_vectors(*args: Any, **kwargs: Any) -> None:
    """Thin wrapper — see ``_bot_pre_agent`` (#1265 Slice 1 PR-5)."""
    await _bot_pre_agent._prepare_pre_agent_retrieval_vectors(*args, **kwargs)


def _new_draft_id() -> int:
    """Thin wrapper — see ``_bot_streaming`` (#1265 Slice 1 PR-4)."""
    return _bot_streaming._new_draft_id()


_AGENT_DRAFT_INTERVAL = _bot_streaming._AGENT_DRAFT_INTERVAL


async def _stream_agent_to_draft(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Thin wrapper — see ``_bot_streaming`` (#1265 Slice 1 PR-4)."""
    return await _bot_streaming._stream_agent_to_draft(
        *args, draft_interval=_AGENT_DRAFT_INTERVAL, **kwargs
    )


def _state_apartment_results(state_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Read cached apartment payloads from legacy or dialog-owned state.

    Implementation lives in :mod:`telegram_bot.observability.state_helpers`
    (card_2a71ec058138, #1265 Slice 1 PR-1). This wrapper preserves the historical
    ``telegram_bot.bot`` import surface for existing callers and tests.
    """
    return _bot_state_helpers._state_apartment_results(state_data)


def _state_control_message_id(state_data: dict[str, Any]) -> int | None:
    """Locate the catalog control message id (legacy or dialog-owned shape).

    Re-exported from :mod:`telegram_bot.observability.state_helpers` (card_2a71ec058138).
    """
    return _bot_state_helpers._state_control_message_id(state_data)


# Re-export from shared module (avoid circular imports with middlewares)
# Re-export checkpointer helpers from shared utility module for backward compat
from .services.util.checkpointer_utils import (  # noqa: E402
    _delete_checkpointer_thread as _delete_checkpointer_thread,
)
from .services.util.checkpointer_utils import (  # noqa: E402
    _supervisor_thread_id as _supervisor_thread_id,
)
from .tracing_context import make_session_id as make_session_id  # noqa: E402


def _extract_current_turn(messages: list[Any]) -> list[Any]:
    """Slice agent checkpointer history down to the current turn (#507).

    Re-exported from :mod:`telegram_bot.observability.state_helpers` (card_2a71ec058138).
    """
    return _bot_state_helpers._extract_current_turn(messages)


def _build_trace_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Build shared metadata dict for trace (text + voice handlers).

    Re-exported from :mod:`telegram_bot.observability.bot_observability` (card_2a71ec058138).
    """
    return _bot_observability._build_trace_metadata(result)


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

    def __init__(self, config: BotConfig, _services: Services | None = None):
        """Initialize bot with services.

        ``_services`` is an optional DI seam for tests: pass a pre-built
        :class:`~telegram_bot.lifecycle.services.Services` instance to skip the
        heavy service construction in
        :func:`~telegram_bot.lifecycle.services.build_services`.
        """
        from .lifecycle.services import build_services  # card_2a71ec058138: homed to lifecycle/

        self.config = config
        self.bot = Bot(token=config.telegram_token)
        self.dp = Dispatcher()

        svc: Services = _services if _services is not None else build_services(config)

        # Unpack services onto bot attributes (preserves existing handler access patterns)
        self._graph_config = svc.graph_config
        self._cache = svc.cache
        self._hybrid = svc.hybrid
        self._embeddings = svc.embeddings
        self._sparse = svc.sparse
        self._qdrant = svc.qdrant
        self._qdrant_apartments = svc.qdrant_apartments
        self._apartments_service = svc.apartments_service
        self._reranker = svc.reranker
        self._llm = svc.llm
        self._apartment_pipeline = svc.apartment_pipeline
        self._redis_monitor = svc.redis_monitor
        self._i18n_hub: Any = svc.i18n_hub

        # Conversation memory checkpointer (initialized in start())
        self._checkpointer: Any = None

        # Agent checkpointer — Redis with TTL (#424).
        # HumanMessage serialization fixed in langgraph-checkpoint-redis>=0.3.6 (#420).
        self._agent_checkpointer: Any = None

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

        self._polling_lock: RedisPollingLock | None = None
        self._polling_lock_task: asyncio.Task[None] | None = None
        self._polling_lock_consecutive_failures: int = 0
        self._polling_lock_owner: str | None = None

        # Track initialization state
        self._cache_initialized = False
        self._pre_agent_filter_extractor: Any | None = None

        # Setup middlewares (before handlers)
        self._setup_middlewares()

        # Register handlers
        self._register_handlers()

    def _get_pre_agent_filter_extractor(self) -> Any:
        """Lazily construct the deterministic extractor used on pre-agent semantic misses."""
        if self._pre_agent_filter_extractor is None:
            from .services.apartment.apartment_filter_extractor import ApartmentFilterExtractor

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
        setup_throttling_middleware(self.dp, default_rate=1.0, admin_ids=self.config.admin_ids)
        setup_error_handler(self.dp)
        self.dp.message.outer_middleware(FSMCancelMiddleware())
        logger.info("Middlewares configured")

    @staticmethod
    def _extract_database_name(database_url: str) -> str | None:
        """Thin wrapper — see ``lifecycle.postgres_bootstrap`` (card_2a71ec058138)."""
        from telegram_bot.lifecycle.postgres_bootstrap import extract_database_name

        return extract_database_name(database_url)

    async def _ensure_postgres_database_exists(
        self, asyncpg_module: Any, database_name: str
    ) -> bool:
        """Thin wrapper — see ``lifecycle.postgres_bootstrap`` (card_2a71ec058138)."""
        from telegram_bot.lifecycle.postgres_bootstrap import ensure_postgres_database_exists

        return await ensure_postgres_database_exists(
            asyncpg_module,
            self.config.realestate_database_url,
            database_name,
        )

    async def _ensure_realestate_schema(self) -> None:
        """Thin wrapper — see ``lifecycle.postgres_bootstrap`` (card_2a71ec058138)."""
        from telegram_bot.lifecycle.postgres_bootstrap import ensure_realestate_schema

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

        # Feedback callbacks (class-method wrappers)
        self.dp.callback_query(FeedbackCB.filter())(self.handle_feedback)
        # Legacy buttons in old chat history may contain "fb:done" (without trailing ':').
        self.dp.callback_query(F.data == "fb:done")(self.handle_feedback)
        self.dp.callback_query(FeedbackReasonCB.filter())(self.handle_feedback_reason)

        # Per-feature handler routers (#2980: decompose PropertyBot god-object)
        from .handlers.crm_callbacks import create_crm_router
        from .handlers.favorites_callbacks import create_favorites_router
        from .handlers.results_callbacks import create_results_router
        from .handlers.service_callbacks import create_service_router

        self.dp.include_router(create_crm_router(self))
        self.dp.include_router(create_service_router(self))
        self.dp.include_router(create_favorites_router(self))
        self.dp.include_router(create_results_router(self))

    async def _resolve_user_role(self, user_id: int) -> str:
        """Resolve user role from DB or config fallback (#388).

        Thin delegate — see ``telegram_bot.handlers.command_handlers.resolve_user_role``.
        """
        from .handlers.command_handlers import resolve_user_role

        return await resolve_user_role(self, user_id)

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_ids

    async def handle_menu_button(
        self,
        message: Message,
        state: FSMContext,
        dialog_manager: Any = None,
        i18n: Any = None,
    ) -> None:
        """Route ReplyKeyboard button press to dedicated handler (#628, #658).

        Thin delegate — see ``telegram_bot.handlers.command_handlers.handle_menu_button``.
        """
        from .handlers.command_handlers import handle_menu_button

        await handle_menu_button(self, message, state, dialog_manager=dialog_manager, i18n=i18n)

    async def _handle_demo(self, message: Message) -> None:
        from .handlers.demo_handler import handle_demo_button

        await handle_demo_button(message)

    async def handle_menu_action_text(self, message: Message, query_text: str) -> None:
        """Dispatch text query to agent pipeline (from ReplyKeyboard context) (#628)."""
        patched = message.model_copy(update={"text": query_text})
        await self.handle_query(patched)

    async def _handle_search(self, message: Message, dialog_manager: Any = None) -> None:
        return await _bot_catalog._handle_search(self, message, dialog_manager)

    async def _handle_services(self, message: Message, i18n: Any = None) -> None:
        return await _bot_catalog._handle_services(self, message, i18n)

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

    async def _handle_bookmarks(self, message: Message, state: FSMContext | None = None) -> None:
        return await _bot_favorites._handle_bookmarks(self, message, state)

    # Mapping callback_data -> query text for RAG pipeline
    _ASK_QUERIES: dict[str, str] = {
        "ask:docs": "Какие документы нужны для покупки?",
        "ask:costs": "Сколько стоит оформление сделки?",
        "ask:vnzh": "Как получить ВНЖ в Болгарии?",
        "ask:installment": "Какие условия рассрочки?",
    }

    async def _handle_ask(
        self,
        message: Message,
        i18n: Any = None,
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_catalog._handle_ask(self, message, i18n, state, dialog_manager)

    async def handle_ask_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_catalog.handle_ask_callback(self, callback, state, dialog_manager)

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

    async def handle_service_callback(self, callback: CallbackQuery, i18n: Any = None) -> None:
        return await _bot_catalog.handle_service_callback(self, callback, i18n)

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

    async def handle_card_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext,
        dialog_manager: Any = None,
    ) -> None:
        return await _bot_catalog.handle_card_callback(self, callback, state, dialog_manager)

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
        from telegram_bot.services.generation.telegram_formatting import send_html_messages

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

    async def handle_feedback(
        self, callback: CallbackQuery, callback_data: FeedbackCB | None = None
    ) -> None:
        """Thin wrapper — see ``_bot_feedback_handlers`` (#2048 PR-9a)."""
        await _bot_feedback_handlers.handle_feedback(self, callback, callback_data)

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

    async def handle_clearcache_callback(self, callback_query: CallbackQuery) -> None:
        """Thin wrapper — see ``_bot_crm_callbacks`` (#2980)."""
        await _bot_crm_callbacks.handle_clearcache_callback(self, callback_query)

    async def handle_menu_action(
        self, callback: CallbackQuery, query_text: str, locale: str = "ru"
    ) -> None:
        """Handle menu button click — dispatch query_text to agent pipeline.

        Thin delegate — see ``telegram_bot.handlers.command_handlers.handle_menu_action``.
        """
        from .handlers.command_handlers import handle_menu_action

        await handle_menu_action(self, callback, query_text, locale=locale)

    # ------------------------------------------------------------------ #
    # Lifecycle helpers — called in order by start()                      #
    # All implementations live in lifecycle/lifecycle (card_2a71ec058138).#
    # ------------------------------------------------------------------ #

    async def _setup_preflight(self) -> tuple[Any, Any]:
        """Run preflight dependency gate; return (preflight_result, startup_report)."""
        return await _bot_lifecycle.setup_preflight(self)

    async def _setup_cache(self) -> None:
        """Initialize Redis cache layer if not already done."""
        await _bot_lifecycle.setup_cache(self)

    async def _setup_checkpointers(self, startup_report: Any) -> None:
        """Initialize conversation and agent Redis checkpointers."""
        await _bot_lifecycle.setup_checkpointers(self, startup_report)

    async def _setup_postgres(self, preflight_result: Any, startup_report: Any) -> None:
        """Initialize PostgreSQL pool, schema, and dependent services."""
        await _bot_lifecycle.setup_postgres(self, preflight_result, startup_report)

    async def _setup_bot_identity(self) -> None:
        """Cache bot user id and detect forum-topics capability."""
        await _bot_lifecycle.setup_bot_identity(self)

    def _setup_handoff_services(self) -> None:
        """Initialize handoff state machine and forum bridge (#730)."""
        _bot_lifecycle.setup_handoff_services(self)

    def _setup_workflow_data(self) -> None:
        """Register runtime services in dp.workflow_data for handler injection."""
        _bot_lifecycle.setup_workflow_data(self)

    def _setup_dialogs(self) -> None:
        """Include all aiogram-dialog routers and the catch-all query handler."""
        _bot_lifecycle.setup_dialogs(self)

    async def _setup_bot_commands(self) -> None:
        """Register bot commands and menu button in Telegram."""
        await _bot_lifecycle.setup_bot_commands(self)

    async def _setup_polling_lock(self) -> None:
        """Acquire Redis polling lock and start heartbeat task."""
        await _bot_lifecycle.setup_polling_lock(self)

    async def start(self):
        """Start bot polling — thin delegate to ``lifecycle.lifecycle.start_bot``."""
        await _bot_lifecycle.start_bot(self)

    async def _warmup_bge(self) -> None:
        """Thin delegate to ``lifecycle.lifecycle.warmup_bge_pool`` (#953)."""
        await _bot_lifecycle.warmup_bge_pool(self._hybrid, log=logger)

    async def _polling_lock_heartbeat_tick(self) -> None:
        """Thin delegate to ``lifecycle.lifecycle.polling_lock_heartbeat_tick``."""
        await _bot_lifecycle.polling_lock_heartbeat_tick(
            self,
            log=logger,
            max_refresh_failures=_POLLING_LOCK_MAX_REFRESH_FAILURES,
        )

    async def stop(self):
        """Stop bot and cleanup — thin delegate to ``lifecycle.lifecycle.stop_bot``."""
        await _bot_lifecycle.stop_bot(self)
