"""Main Telegram bot logic — legacy graph pipeline.

Module-level helpers were extracted to focused submodules in slice 1 of
the ``PropertyBot`` decomposition (issue #1265 / #2046). The thin
wrappers below preserve the historical ``from telegram_bot.bot import X``
import surface for tests that ``patch("telegram_bot.bot.X", ...)``.

Slice 1 extraction map:

* ``_bot_state_helpers`` (#1265 PR-1) — apartment-list and catalog-control
  message-id reads (``_state_apartment_results``,
  ``_state_control_message_id``, ``_extract_current_turn``).
* ``_bot_observability`` (#1265 PR-2) — trace metadata builder
  (``_build_trace_metadata``).
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
import logging
import os
import socket
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F
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
    _bot_crm_callbacks,  # #2980: extracted clearcache callback handler
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
from .keyboards.client_keyboard import (
    parse_menu_button,
)
from .middlewares import setup_error_handler, setup_throttling_middleware
from .middlewares.fsm_cancel import FSMCancelMiddleware
from .observability import (
    propagate_attributes,
)
from .services.forum_bridge import ForumBridge
from .startup_status import StartupReport, StartupSeverity, StartupSignal


class GraphRecursionError(RuntimeError):
    """Compatibility exception after legacy graph removal."""


if TYPE_CHECKING:
    from ._bot_services import Services
    from .agents.context import BotContext as BotContextType
    from .pipelines.state_contract import PreAgentStateContract
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
    """Build shared metadata dict for trace (text + voice handlers).

    Re-exported from :mod:`telegram_bot._bot_observability` (#1265 Slice 1 PR-2).
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
        :class:`~telegram_bot._bot_services.Services` instance to skip the
        heavy service construction in
        :func:`~telegram_bot._bot_services.build_services`.
        """
        from ._bot_services import build_services

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

    async def _handle_ask(self, message: Message, i18n: Any = None) -> None:
        return await _bot_catalog._handle_ask(self, message, i18n)

    async def handle_ask_callback(self, callback: CallbackQuery) -> None:
        return await _bot_catalog.handle_ask_callback(self, callback)

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

    # _send_hitl_confirmation removed — dead code, no live callers (#2943)

    async def handle_hitl_callback(self, callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer("Устарело")

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
            callbacks: list[Any] = []
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

    # ------------------------------------------------------------------ #
    # Lifecycle helpers — called in order by start()                      #
    # ------------------------------------------------------------------ #

    async def _setup_preflight(self) -> tuple[Any, StartupReport]:
        """Run preflight dependency gate; return (preflight_result, startup_report)."""
        startup_report = StartupReport()
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
        return preflight_result, startup_report

    async def _setup_cache(self) -> None:
        """Initialize Redis cache layer if not already done."""
        if not self._cache_initialized:
            logger.info("Initializing cache service...")
            await self._cache.initialize()
            self._cache_initialized = True
            logger.info("Cache service ready")

    async def _setup_checkpointers(self, startup_report: StartupReport) -> None:
        """Initialize conversation and agent Redis checkpointers."""
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

        # Agent checkpointer — Redis with TTL for bounded retention (#424).
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

    async def _setup_postgres(self, preflight_result: Any, startup_report: StartupReport) -> None:
        """Initialize PostgreSQL pool, schema, and dependent services."""
        postgres_available = (
            preflight_result.get("postgres", True) if isinstance(preflight_result, dict) else True
        )
        if not postgres_available:
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
            return

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

    async def _setup_bot_identity(self) -> None:
        """Cache bot user id and detect forum-topics capability."""
        try:
            me = await self.bot.me()
            self._bot_user_id = me.id
        except Exception:
            logger.warning("Failed to cache bot user id")

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

    def _setup_handoff_services(self) -> None:
        """Initialize handoff state machine and forum bridge (#730)."""
        if self._cache.redis is None:
            return
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

    def _setup_workflow_data(self) -> None:
        """Register runtime services in dp.workflow_data for handler injection."""
        from .middlewares.i18n import setup_i18n_middleware

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

        if self._i18n_hub is not None:
            setup_i18n_middleware(self.dp, self._i18n_hub, self._user_service)
            logger.info("i18n middleware ready")
        else:
            logger.warning("i18n hub unavailable; running without i18n middleware")

    def _setup_dialogs(self) -> None:
        """Include all aiogram-dialog routers and the catch-all query handler."""
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

        # Catch-all text handler — AFTER dialog routers (first-match wins).
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

    async def _setup_bot_commands(self) -> None:
        """Register bot commands and menu button in Telegram."""
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
        from aiogram.types import MenuButtonCommands

        await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    async def _setup_polling_lock(self) -> None:
        """Acquire Redis polling lock and start heartbeat task."""
        if self._cache.redis is None:
            return
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

    async def start(self):
        """Start bot polling."""
        logger.info("Starting bot...")

        preflight_result, startup_report = await self._setup_preflight()
        await self._setup_cache()
        await self._setup_checkpointers(startup_report)
        await self._setup_postgres(preflight_result, startup_report)
        await self._setup_bot_identity()
        self._setup_handoff_services()
        self._setup_workflow_data()
        self._setup_dialogs()
        await self._setup_bot_commands()

        # Start Redis health monitor (background task, every 5 min)
        await self._redis_monitor.start()

        # Warm up BGE-M3 connection pool (#953)
        await self._warmup_bge()

        if startup_report.final_severity is StartupSeverity.FAILED:
            logger.error(startup_report.render())
        elif startup_report.final_severity is StartupSeverity.DEGRADED:
            logger.warning(startup_report.render())
        else:
            logger.info(startup_report.render())

        await self._setup_polling_lock()

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
        await self.bot.session.close()
