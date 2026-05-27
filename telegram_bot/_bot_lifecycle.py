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

The class methods on ``PropertyBot`` (``_warmup_bge`` and
``_polling_lock_heartbeat_tick``) become thin delegates: they exist so
the existing ``await bot._warmup_bge()`` / ``await
bot._polling_lock_heartbeat_tick()`` call sites and their unit tests
keep working without touching their signatures.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:  # pragma: no cover - typing-only
    from logging import Logger


__all__ = ("polling_lock_heartbeat_tick", "warmup_bge_pool")


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
