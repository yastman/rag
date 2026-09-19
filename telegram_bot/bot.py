"""Main Telegram bot logic — PropertyBot thin orchestrator.

Module-level helpers are extracted to focused ``_bot_*`` submodules and
lifecycle/observability subpackages.
Shared capabilities are imported from their canonical modules.

Extraction map:
  observability/state_helpers (card_2a71ec058138, #1265 PR-1),
  pipeline/streaming (#1265 PR-4, card_2a71ec058138 SLICE 3),
  pipeline/supervisor (#2816 Slice 2, card_2a71ec058138 SLICE 3),
  lifecycle/lifecycle (card_2a71ec058138),
  handlers/{catalog,favorites,bot_handoff,bot_crm_callbacks,feedback_handlers} (card_2a71ec058138 SLICE 2),
  handlers/command_handlers (card_c6ade99aada1).
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
)

from src.runtime.integrations.polling_lock import RedisPollingLock
from src.services.handoff_state import HandoffState

from .callback_data import FeedbackCB, FeedbackReasonCB
from .config import BotConfig
from .handlers import (
    bot_handoff as _bot_handoff,  # #2816 Slice 2: extracted handoff handlers
)
from .handlers import command_handlers
from .handlers import (
    feedback_handlers as _bot_feedback_handlers,  # #2048 PR-9a: extracted feedback callback handlers
)
from .lifecycle import lifecycle as _bot_lifecycle  # card_2a71ec058138: homed to lifecycle/
from .middlewares import setup_error_handler, setup_throttling_middleware
from .middlewares.fsm_cancel import FSMCancelMiddleware
from .middlewares.update_dedup import UpdateDeduplicationMiddleware
from .pipeline import (
    supervisor as _bot_query_pipeline,  # card_2a71ec058138 SLICE 3: moved to pipeline/
)
from .services.forum_bridge import ForumBridge


class GraphRecursionError(RuntimeError):
    """Compatibility exception after legacy graph removal."""


if TYPE_CHECKING:
    from .lifecycle.services import Services  # card_2a71ec058138: homed to lifecycle/
else:
    Services = Any

logger = logging.getLogger(__name__)

# --- Checkpoint namespace constants (versioned for safe migration) ---
_APARTMENT_PAGE_SIZE = 5
_NO_RAG_QUERY_TYPES: frozenset[str] = frozenset({"CHITCHAT", "OFF_TOPIC"})


# Re-export from shared module (avoid circular imports with middlewares)
from .observability.context import make_session_id as make_session_id  # noqa: E402


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

        # User service (asyncpg) — initialized in start()
        self._user_service: Any = None

        # PostgreSQL pool — initialized in start()
        self._pg_pool: Any = None

        # Favorites service (initialized in start() with pg_pool)
        self._favorites_service: Any = None

        # Search event store (initialized in start() with pg_pool)
        self._search_event_store: Any | None = None

        # Feedback event store (initialized in setup_postgres with pg_pool, #3422)
        self._feedback_store: Any | None = None

        # Handoff services (Forum Topics bridge + Redis state machine)
        self._handoff_state: HandoffState | None = None
        self._forum_bridge: ForumBridge | None = None
        self._bot_user_id: int | None = None

        # Durable sink behind phone-collected lead requests (#3213)
        self._lead_sink: Any | None = None

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
        self.dp.update.outer_middleware(UpdateDeduplicationMiddleware())
        setup_throttling_middleware(self.dp, default_rate=1.0, admin_ids=self.config.admin_ids)
        setup_error_handler(self.dp)
        self.dp.message.outer_middleware(FSMCancelMiddleware())
        logger.info("Middlewares configured")

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
            )(partial(_bot_handoff._handle_group_message, self))

        # Command handlers Router (extracted from class methods)
        from .handlers.command_handlers import create_commands_router

        self.dp.include_router(create_commands_router(self))
        from .keyboards.client_keyboard import get_menu_button_texts

        menu_button_texts = tuple(get_menu_button_texts(self._i18n_hub))
        self.dp.message(
            F.text.in_(menu_button_texts),
            flags={"rate_limit": {"rate": 0.6, "key": "menu"}},
        )(partial(command_handlers.handle_menu_button, self))
        # NOTE: catch-all handle_query is registered on self._catch_all_router
        # which is included AFTER dialog routers in _setup_dialogs().
        # This ensures dialog MessageInput (e.g. viewing phone input)
        # is resolved before the catch-all (aiogram SDK: first-match wins).
        # Demo flow router
        from .handlers.demo_handler import create_demo_router

        self.dp.include_router(create_demo_router())

        # Feedback callbacks (class-method wrappers)
        self.dp.callback_query(FeedbackCB.filter())(
            partial(_bot_feedback_handlers.handle_feedback, self)
        )
        # Legacy buttons in old chat history may contain "fb:done" (without trailing ':').
        self.dp.callback_query(F.data == "fb:done")(
            partial(_bot_feedback_handlers.handle_feedback, self)
        )
        self.dp.callback_query(FeedbackReasonCB.filter())(
            partial(_bot_feedback_handlers.handle_feedback_reason, self)
        )

        # Per-feature handler routers (#2980: decompose PropertyBot god-object)
        from .handlers.crm_callbacks import create_crm_router
        from .handlers.favorites_callbacks import create_favorites_router
        from .handlers.results_callbacks import create_results_router
        from .handlers.service_callbacks import create_service_router

        self.dp.include_router(create_crm_router(self))
        self.dp.include_router(create_service_router(self))
        self.dp.include_router(create_favorites_router(self))
        self.dp.include_router(create_results_router(self))

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_ids

    @property
    def forum_handoff_available(self) -> bool:
        """Interactive Forum handoff is explicitly enabled and fully configured (#3239).

        Requires ``HANDOFF_ENABLED`` plus the Forum Topics bridge (managers
        group) and the Redis handoff state. When False, manager buttons route
        to the durable phone-request sink instead of the qualification dialog —
        the bot never starts a forum handoff it cannot finish.
        """
        # Defensive getattr: partially constructed instances in tests.
        config = getattr(self, "config", None)
        return (
            bool(getattr(config, "handoff_enabled", False))
            and getattr(self, "_forum_bridge", None) is not None
            and getattr(self, "_handoff_state", None) is not None
        )

    async def handle_menu_action_text(self, message: Message, query_text: str) -> None:
        """Dispatch text query to agent pipeline (from ReplyKeyboard context) (#628)."""
        patched = message.model_copy(update={"text": query_text})
        await _bot_query_pipeline.handle_query(self, patched)

    # Mapping callback_data -> query text for RAG pipeline
    _ASK_QUERIES: dict[str, str] = {
        "ask:docs": "Какие документы нужны для покупки?",
        "ask:costs": "Сколько стоит оформление сделки?",
        "ask:vnzh": "Как получить ВНЖ в Болгарии?",
        "ask:installment": "Какие условия рассрочки?",
    }

    # ------------------------------------------------------------------ #
    # Lifecycle helpers — called in order by start()                      #
    # All implementations live in lifecycle/lifecycle (card_2a71ec058138).#
    # ------------------------------------------------------------------ #

    async def start(self):
        """Start bot polling — thin delegate to ``lifecycle.lifecycle.start_bot``."""
        await _bot_lifecycle.start_bot(self)

    async def stop(self):
        """Stop bot and cleanup — thin delegate to ``lifecycle.lifecycle.stop_bot``."""
        await _bot_lifecycle.stop_bot(self)
