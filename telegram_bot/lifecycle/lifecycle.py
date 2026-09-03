"""Lifecycle helpers extracted from ``telegram_bot/bot.py`` (#2048).

PR-8 of the Slice 2 decomposition plan
(``docs/engineering/bot-decomposition-plan-2026-05-27.md``). Owns the
two pure-ish lifecycle helpers that ``PropertyBot.start`` /
``PropertyBot.stop`` invoke, so they can be tested without
instantiating the full bot stack.

Module-level imports are stdlib only; the helpers receive their
collaborators (the hybrid embedder, the polling-lock state holder) as
arguments instead of reading ``self`` directly. This keeps the import
graph narrow — no ``aiogram`` / ``langgraph`` / ``qdrant_client`` /
``fastapi`` at module scope, pinned by
``tests/contract/test_bot_lifecycle_extraction_contract.py``.

Owned helpers (verbatim, byte-for-byte semantics with the pre-extract
``bot.py`` definitions):

  - :func:`warmup_bge_pool` — warm BGE-M3 connection pool (#953).
  - :func:`polling_lock_heartbeat_tick` — single Redis polling-lock
    heartbeat tick with bounded retry/give-up behaviour.

  Setup/teardown helpers (card_c6ade99aada1 — decompose PropertyBot):

  - :func:`setup_preflight` — preflight dependency gate.
  - :func:`setup_cache` — Redis cache layer init.
  - :func:`setup_postgres` — PostgreSQL pool + schema + services.
  - :func:`setup_bot_identity` — cache bot user id, detect topics.
  - :func:`setup_handoff_services` — handoff state machine + forum bridge.
  - :func:`setup_workflow_data` — register services in dp.workflow_data.
  - :func:`setup_dialogs` — include aiogram-dialog routers + catch-all.
  - :func:`setup_bot_commands` — register Telegram bot commands.
  - :func:`setup_polling_lock` — acquire Redis polling lock + heartbeat.
  - :func:`start_bot` — full startup sequence.
  - :func:`stop_bot` — graceful teardown.

The class methods on ``PropertyBot`` (``_warmup_bge``,
``_polling_lock_heartbeat_tick``, ``_setup_*``, ``start``, ``stop``)
become thin delegates: they exist so existing call sites and tests keep
working without touching their signatures.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:  # pragma: no cover - typing-only
    from logging import Logger


__all__ = (
    "polling_lock_heartbeat_tick",
    "setup_bot_commands",
    "setup_bot_identity",
    "setup_cache",
    "setup_dialogs",
    "setup_handoff_services",
    "setup_polling_lock",
    "setup_postgres",
    "setup_preflight",
    "setup_workflow_data",
    "start_bot",
    "stop_bot",
    "warmup_bge_pool",
)


# Maximum consecutive Redis polling-lock heartbeat failures tolerated before we
# stop polling. Mirrors ``telegram_bot.bot._POLLING_LOCK_MAX_REFRESH_FAILURES``;
# kept here so the helper is self-contained and the contract test does not
# have to reach back into ``bot.py`` for a constant.
POLLING_LOCK_MAX_REFRESH_FAILURES = 2


class _HasAembedQuery(Protocol):
    async def aembed_query(self, text: str) -> Any: ...  # pragma: no cover


class _PollingLockState(Protocol):
    """Minimal protocol the heartbeat helper needs.

    The protocol exists for documentation only — ``PropertyBot`` instances
    satisfy it structurally; tests can pass any object exposing the same
    attributes/methods.
    """

    _polling_lock: Any
    _polling_lock_consecutive_failures: int
    dp: Any  # aiogram Dispatcher with ``stop_polling`` (awaited under the hood)


async def warmup_bge_pool(
    hybrid: _HasAembedQuery,
    *,
    log: Logger | None = None,
) -> None:
    """Warm up the BGE-M3 connection pool (#953).

    Issues a single ``aembed_query("warmup")`` against the supplied
    hybrid embedder. Failures are non-fatal: they are logged at
    ``WARNING`` and the helper returns normally so that bot startup is
    not blocked when BGE-M3 is briefly unavailable.

    Parameters
    ----------
    hybrid:
        Object exposing the async ``aembed_query`` method
        (typically the ``HybridEmbedder`` wired into ``PropertyBot``).
    log:
        Optional logger override. Defaults to the lifecycle module's
        own logger so the message origin is unambiguous.
    """
    log = log or logging.getLogger(__name__)
    try:
        await hybrid.aembed_query("warmup")
        log.info("BGE-M3 warmup complete")
    except Exception:
        log.warning("BGE-M3 warmup failed (will retry on first query)", exc_info=True)


async def polling_lock_heartbeat_tick(
    bot: Any,
    *,
    log: Logger | None = None,
    max_refresh_failures: int = POLLING_LOCK_MAX_REFRESH_FAILURES,
) -> None:
    """Single Redis polling-lock heartbeat tick.

    Refreshes the polling lock if one is held. On transient failure the
    consecutive-failure counter is incremented and the next tick will
    retry; once ``max_refresh_failures`` is reached the helper stops
    polling on the bot's dispatcher so the lease can't silently expire.

    The helper mutates ``bot._polling_lock_consecutive_failures`` in
    place (matching the legacy method). Pass any object satisfying the
    :class:`_PollingLockState` protocol — the tests use a plain
    ``MagicMock`` standing in for ``PropertyBot``.
    """
    log = log or logging.getLogger(__name__)
    if bot._polling_lock is None:
        return
    try:
        await bot._polling_lock.refresh()
        bot._polling_lock_consecutive_failures = 0
    except Exception:
        bot._polling_lock_consecutive_failures += 1
        if bot._polling_lock_consecutive_failures < max_refresh_failures:
            log.warning(
                "Polling lock heartbeat refresh failed (%d/%d); retrying",
                bot._polling_lock_consecutive_failures,
                max_refresh_failures,
                exc_info=True,
            )
            return
        log.exception(
            "Polling lock heartbeat failed %d times; stopping polling",
            max_refresh_failures,
        )
        with contextlib.suppress(Exception):
            await bot.dp.stop_polling()


# ---------------------------------------------------------------------------
# Setup / teardown helpers (card_c6ade99aada1 — decompose PropertyBot)
# All heavy imports are deferred into function bodies to keep the module-scope
# import graph stdlib-only (contract: test_bot_lifecycle_extraction_contract.py).
# ---------------------------------------------------------------------------


async def setup_preflight(bot: Any) -> tuple[Any, Any]:
    """Run preflight dependency gate; return (preflight_result, startup_report).

    Mirrors ``PropertyBot._setup_preflight``.
    """
    from telegram_bot.startup_status import StartupReport

    startup_report = StartupReport()
    from telegram_bot.preflight import PreflightError, check_dependencies

    try:
        preflight_result = await check_dependencies(bot.config, log_summary=False)
    except PreflightError as exc:
        startup_report.merge(exc.report)
        logging.getLogger(__name__).error(startup_report.render())
        raise
    preflight_report = getattr(preflight_result, "report", None)
    if isinstance(preflight_report, startup_report.__class__):
        startup_report.merge(preflight_report)
    return preflight_result, startup_report


async def setup_cache(bot: Any) -> None:
    """Initialize Redis cache layer if not already done."""
    log = logging.getLogger(__name__)
    if not bot._cache_initialized:
        log.info("Initializing cache service...")
        await bot._cache.initialize()
        bot._cache_initialized = True
        log.info("Cache service ready")


async def setup_postgres(bot: Any, preflight_result: Any, startup_report: Any) -> None:
    """Initialize PostgreSQL pool, schema, and dependent services."""
    from telegram_bot.startup_status import StartupSeverity, StartupSignal

    log = logging.getLogger(__name__)
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
        log.info("Skipping PostgreSQL pool init because preflight already marked it unavailable")
        return

    try:
        import asyncpg

        test_conn: Any | None = None
        try:
            test_conn = await asyncpg.connect(bot.config.realestate_database_url, timeout=5)
        except asyncpg.InvalidCatalogNameError:
            target_db = bot._extract_database_name(bot.config.realestate_database_url)
            if target_db is None:
                raise
            log.warning("PostgreSQL database %s missing; attempting auto-create", target_db)
            if not await bot._ensure_postgres_database_exists(asyncpg, target_db):
                raise
            test_conn = await asyncpg.connect(bot.config.realestate_database_url, timeout=5)
        finally:
            if test_conn is not None:
                await test_conn.close()

        bot._pg_pool = await asyncpg.create_pool(
            bot.config.realestate_database_url,
            min_size=0,
            max_size=5,
            timeout=5,
        )
        log.info("PostgreSQL pool ready (realestate)")
        await bot._ensure_realestate_schema()
        log.info("PostgreSQL schema ready (realestate)")

        from telegram_bot.services.favorites_service import FavoritesService
        from telegram_bot.services.observability.search_event_store import SearchEventStore
        from telegram_bot.services.user_service import UserService

        bot._user_service = UserService(pool=bot._pg_pool)
        bot._favorites_service = FavoritesService(pool=bot._pg_pool)
        log.info("Favorites service ready")
        bot._search_event_store = SearchEventStore(pool=bot._pg_pool)
        log.info("Search event store ready")

    except Exception:
        log.warning("PostgreSQL pool init failed, user features disabled", exc_info=True)
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


async def setup_bot_identity(bot: Any) -> None:
    """Cache bot user id and detect forum-topics capability."""
    log = logging.getLogger(__name__)
    try:
        me = await bot.bot.me()
        bot._bot_user_id = me.id
    except Exception:
        log.warning("Failed to cache bot user id")

    try:
        me = await bot.bot.get_me()
        if not getattr(me, "has_topics_enabled", False):
            log.warning(
                "Forum topics not enabled for this bot. "
                "Enable 'Topics in Private Chats' via BotFather Mini App. "
                "Thread routing will be disabled."
            )
            bot._topics_enabled = False
        else:
            bot._topics_enabled = True
            log.info("Forum topics mode: enabled")
    except Exception:
        log.warning("Failed to check forum topics status", exc_info=True)
        bot._topics_enabled = False


def setup_handoff_services(bot: Any) -> None:
    """Initialize handoff state machine and forum bridge (#730)."""
    from src.services.handoff_state import HandoffState
    from telegram_bot.services.forum_bridge import ForumBridge
    from telegram_bot.services.lead_sink import LeadRequestSink

    log = logging.getLogger(__name__)
    if bot._cache.redis is None:
        return
    bot._handoff_state = HandoffState(
        bot._cache.redis,
        ttl_hours=bot.config.handoff_ttl_hours,
    )
    if bot.config.managers_group_id:
        bot._forum_bridge = ForumBridge(
            bot=bot.bot,
            managers_group_id=bot.config.managers_group_id,
        )
        log.info(
            "Forum Topics bridge enabled (managers_group_id=%s)",
            bot.config.managers_group_id,
        )
    # Interactive manager handoff is capability-gated (#3239): it starts only
    # when HANDOFF_ENABLED is set AND the bridge AND the Redis state exist.
    # The bridge itself stays available to the #3213 lead-request sink.
    if (
        bot.config.handoff_enabled
        and bot._forum_bridge is not None
        and bot._handoff_state is not None
    ):
        log.info("Manager handoff capability: enabled (forum + Redis state ready)")
    else:
        log.warning(
            "Manager handoff capability: disabled (handoff_enabled=%s, bridge=%s, "
            "redis_state=%s) — manager buttons fall back to the phone-request sink",
            bot.config.handoff_enabled,
            bot._forum_bridge is not None,
            bot._handoff_state is not None,
        )
    # Durable sink behind phone-collected lead requests (#3213). Without it
    # the collector must not confirm that a request was created.
    bot._lead_sink = LeadRequestSink(
        redis=bot._cache.redis,
        forum_bridge=bot._forum_bridge,
    )
    log.info(
        "Lead request sink enabled (manager_notification=%s)",
        bot._forum_bridge is not None,
    )


def setup_workflow_data(bot: Any) -> None:
    """Register runtime services in dp.workflow_data for handler injection."""
    from telegram_bot.middlewares.i18n import setup_i18n_middleware

    log = logging.getLogger(__name__)
    bot.dp["user_service"] = bot._user_service
    bot.dp["pg_pool"] = bot._pg_pool
    bot.dp["bot_config"] = bot.config
    bot.dp["property_bot"] = bot
    bot.dp["apartments_service"] = bot._apartments_service
    bot.dp["favorites_service"] = bot._favorites_service
    bot.dp["search_event_store"] = bot._search_event_store
    bot.dp["lead_sink"] = bot._lead_sink
    bot.dp["pipeline"] = bot._apartment_pipeline
    bot.dp["embeddings"] = bot._hybrid
    bot.dp["llm"] = bot._llm

    if bot._i18n_hub is not None:
        setup_i18n_middleware(bot.dp, bot._i18n_hub, bot._user_service)
        log.info("i18n middleware ready")
    else:
        log.warning("i18n hub unavailable; running without i18n middleware")


def setup_dialogs(bot: Any) -> None:
    """Include all aiogram-dialog routers and the catch-all query handler."""
    from aiogram import F
    from aiogram import Router as _Router
    from aiogram.filters import StateFilter
    from aiogram_dialog import setup_dialogs as aiogram_setup_dialogs

    from telegram_bot.dialogs.catalog import catalog_dialog
    from telegram_bot.dialogs.client_menu import client_menu_dialog
    from telegram_bot.dialogs.demo import demo_dialog
    from telegram_bot.dialogs.faq import faq_dialog
    from telegram_bot.dialogs.filter_dialog import filter_dialog
    from telegram_bot.dialogs.funnel import funnel_dialog
    from telegram_bot.dialogs.handoff import handoff_dialog
    from telegram_bot.dialogs.settings import settings_dialog
    from telegram_bot.dialogs.viewing import viewing_dialog

    log = logging.getLogger(__name__)

    bot.dp.include_router(client_menu_dialog)
    bot.dp.include_router(catalog_dialog)
    bot.dp.include_router(settings_dialog)
    bot.dp.include_router(demo_dialog)
    bot.dp.include_router(funnel_dialog)
    bot.dp.include_router(filter_dialog)
    bot.dp.include_router(faq_dialog)
    bot.dp.include_router(viewing_dialog)
    bot.dp.include_router(handoff_dialog)

    # Catch-all text handler — AFTER dialog routers (first-match wins).
    bot._catch_all_router = _Router(name="catch_all_query")
    bot._catch_all_router.message(
        StateFilter(None),
        F.text,
        flags={"rate_limit": {"rate": 2.0, "key": "query"}},
    )(bot.handle_query)
    bot.dp.include_router(bot._catch_all_router)

    aiogram_setup_dialogs(bot.dp)
    log.info("aiogram-dialog setup complete")


async def setup_bot_commands(bot: Any) -> None:
    """Register bot commands and menu button in Telegram."""
    from aiogram.types import BotCommand, MenuButtonCommands

    await bot.bot.set_my_commands(
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
    await bot.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def setup_polling_lock(bot: Any) -> None:
    """Acquire Redis polling lock and start heartbeat task."""
    import asyncio
    import os
    import socket

    from src.runtime.integrations.polling_lock import POLLING_LOCK_KEY, RedisPollingLock

    log = logging.getLogger(__name__)
    if bot._cache.redis is None:
        return
    bot._polling_lock = RedisPollingLock(
        redis=bot._cache.redis,
        key=POLLING_LOCK_KEY,
    )
    bot._polling_lock_owner = f"{socket.gethostname()}:{os.getpid()}"
    await bot._polling_lock.acquire(bot._polling_lock_owner)
    refresh_interval = max(1, bot._polling_lock.ttl_sec // 3)
    bot._polling_lock_consecutive_failures = 0

    async def _polling_lock_heartbeat_loop() -> None:
        while True:
            await asyncio.sleep(refresh_interval)
            try:
                await bot._polling_lock_heartbeat_tick()
            except Exception:
                log.exception("Polling lock heartbeat loop error")

    bot._polling_lock_task = asyncio.create_task(
        _polling_lock_heartbeat_loop(), name="polling-lock-heartbeat"
    )


async def start_bot(bot: Any) -> None:
    """Full startup sequence for PropertyBot.

    Mirrors ``PropertyBot.start``.
    """
    import asyncio
    import contextlib

    from telegram_bot.startup_status import StartupSeverity

    log = logging.getLogger(__name__)
    log.info("Starting bot...")

    preflight_result, startup_report = await setup_preflight(bot)
    await setup_cache(bot)
    await setup_postgres(bot, preflight_result, startup_report)
    await setup_bot_identity(bot)
    setup_handoff_services(bot)
    setup_workflow_data(bot)
    setup_dialogs(bot)
    await setup_bot_commands(bot)

    await bot._redis_monitor.start()
    await warmup_bge_pool(bot._hybrid, log=log)

    if startup_report.final_severity is StartupSeverity.FAILED:
        log.error(startup_report.render())
    elif startup_report.final_severity is StartupSeverity.DEGRADED:
        log.warning(startup_report.render())
    else:
        log.info(startup_report.render())

    await setup_polling_lock(bot)

    try:
        await bot.dp.start_polling(bot.bot)
    finally:
        if bot._polling_lock_task is not None:
            bot._polling_lock_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bot._polling_lock_task
            bot._polling_lock_task = None


async def stop_bot(bot: Any) -> None:
    """Graceful teardown for PropertyBot.

    Mirrors ``PropertyBot.stop``.
    """
    import asyncio
    import contextlib

    log = logging.getLogger(__name__)
    log.info("Stopping bot...")

    if bot._polling_lock_task is not None:
        bot._polling_lock_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bot._polling_lock_task
        bot._polling_lock_task = None
    if bot._polling_lock is not None and bot._polling_lock_owner is not None:
        try:
            await bot._polling_lock.release()
        except Exception:
            log.warning("Failed to release polling lock cleanly", exc_info=True)
        finally:
            bot._polling_lock = None
            bot._polling_lock_owner = None
    await bot._redis_monitor.stop()
    await bot._cache.close()
    await bot._qdrant.close()
    if hasattr(bot._embeddings, "aclose"):
        await bot._embeddings.aclose()
    if hasattr(bot._sparse, "aclose"):
        await bot._sparse.aclose()
    if bot._reranker and hasattr(bot._reranker, "close"):
        await bot._reranker.close()
    bot._pre_agent_filter_extractor = None
    if bot._pg_pool is not None:
        await bot._pg_pool.close()
        log.info("PostgreSQL pool closed")
    await bot.bot.session.close()
