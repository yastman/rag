"""Checkpointer factory for LangGraph conversation persistence.

Uses AsyncRedisSaver (langgraph-checkpoint-redis SDK) when Redis URL is configured.
Falls back to MemorySaver for dev/testing. Zero custom logic — SDK wiring only.

Direct checkpoint overhead measurement (#1258)
----------------------------------------------
The Redis saver returned by :func:`create_redis_checkpointer` is wrapped in
:class:`InstrumentedCheckpointer`, which times the four hot async methods
(``aput`` / ``aget`` / ``aput_writes`` / ``aget_tuple``) and accumulates the
durations into a per-invoke :class:`contextvars.ContextVar` bucket. Callers
that wrap an ``ainvoke`` with :func:`begin_checkpoint_overhead_capture` /
:func:`end_checkpoint_overhead_capture` get the *direct* sum of checkpoint
I/O time rather than the previous derived proxy
(``ainvoke_wall_ms - sum_of_stage_latencies``) which also captured Pregel
loop and ``@observe`` decorator overhead.

LangGraph compatibility (#2147)
-------------------------------
:class:`InstrumentedCheckpointer` subclasses
:class:`langgraph.checkpoint.base.BaseCheckpointSaver` so LangGraph's
``ensure_valid_checkpointer`` (which uses ``isinstance``) accepts the wrapper.
All :class:`BaseCheckpointSaver` methods are explicitly delegated to the
wrapped saver; the four hot async I/O methods are intercepted to record
direct latency. Saver-specific helpers (e.g. ``asetup`` on AsyncRedisSaver)
are still resolved lazily via ``__getattr__``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Collection, Iterator, Sequence
from contextvars import ContextVar
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Direct checkpointer overhead measurement (#1258)
# -----------------------------------------------------------------------------

#: Per-invoke bucket of checkpoint operation durations and call count.
#: ``None`` means capture is not active (operations pass through untimed).
_checkpoint_op_bucket: ContextVar[dict[str, float] | None] = ContextVar(
    "checkpoint_op_bucket", default=None
)

#: Methods we measure on the wrapped checkpointer. These are the four async
#: I/O entry points exposed by every LangGraph saver implementation; together
#: they account for all per-invoke checkpoint reads and writes.
_INSTRUMENTED_METHODS: tuple[str, ...] = (
    "aput",
    "aget",
    "aput_writes",
    "aget_tuple",
)


def begin_checkpoint_overhead_capture() -> dict[str, float]:
    """Start a per-invoke direct measurement of checkpoint I/O latency (#1258).

    Returns the fresh bucket so the caller can pass it back into
    :func:`end_checkpoint_overhead_capture` without re-reading the ContextVar.
    Safe to call when the underlying checkpointer is not instrumented — the
    bucket is set, but no operations populate it, so
    :func:`end_checkpoint_overhead_capture` returns an empty bucket.
    """
    bucket: dict[str, float] = {f"{m}_ms": 0.0 for m in _INSTRUMENTED_METHODS}
    bucket["calls"] = 0.0
    _checkpoint_op_bucket.set(bucket)
    return bucket


def end_checkpoint_overhead_capture() -> dict[str, float] | None:
    """Stop the capture started by :func:`begin_checkpoint_overhead_capture`.

    Returns the populated bucket, or ``None`` if no capture was active.
    Sum of ``*_ms`` keys is the direct checkpoint overhead in milliseconds.
    """
    bucket = _checkpoint_op_bucket.get()
    _checkpoint_op_bucket.set(None)
    return bucket


def sum_checkpoint_overhead_ms(bucket: dict[str, float] | None) -> float:
    """Sum the per-method durations in *bucket* (ignoring the ``calls`` counter)."""
    if not bucket:
        return 0.0
    return sum(float(v) for k, v in bucket.items() if k.endswith("_ms"))


def _record(name: str, elapsed_ms: float) -> None:
    """Accumulate a single instrumented call into the active capture bucket.

    Fail-soft: any error here MUST NOT propagate into the wrapped call.
    """
    bucket = _checkpoint_op_bucket.get()
    if bucket is None:
        return
    try:
        bucket[f"{name}_ms"] = bucket.get(f"{name}_ms", 0.0) + elapsed_ms
        bucket["calls"] = bucket.get("calls", 0.0) + 1.0
    except Exception:  # pragma: no cover — defensive only
        logger.debug(
            "InstrumentedCheckpointer._record failed for %s",
            name,
            exc_info=True,
        )


class InstrumentedCheckpointer(BaseCheckpointSaver[Any]):
    """Time the four hot checkpoint methods and accumulate durations (#1258).

    Subclasses :class:`BaseCheckpointSaver` (#2147) so LangGraph's
    ``ensure_valid_checkpointer`` (``isinstance``-based) accepts the wrapper.
    Every :class:`BaseCheckpointSaver` method is explicitly delegated to the
    wrapped saver. The four hot I/O methods (``aput``, ``aget``,
    ``aput_writes``, ``aget_tuple``) record their wall time into the active
    :data:`_checkpoint_op_bucket` ContextVar; capture is gated so concurrent
    ``ainvoke`` calls in the same event loop each accumulate into their own
    bucket without cross-talk.
    """

    def __init__(self, saver: BaseCheckpointSaver[Any]) -> None:
        # Do NOT call ``super().__init__()`` — that would install a fresh
        # JsonPlusSerializer on ``self``. We mirror the wrapped saver's
        # serializer instead so behaviour stays identical.
        self._saver = saver
        self.serde = saver.serde

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"InstrumentedCheckpointer({self._saver!r})"

    def __getattr__(self, name: str) -> Any:
        # __getattr__ runs only when normal attribute lookup misses. This
        # exposes saver-specific helpers like ``asetup`` (AsyncRedisSaver)
        # without enumerating every concrete saver's API surface here.
        # Use object.__getattribute__ to avoid recursion if ``_saver``
        # itself is missing during init.
        try:
            saver = object.__getattribute__(self, "_saver")
        except AttributeError:
            raise AttributeError(name) from None
        return getattr(saver, name)

    # -------------------------------------------------------------------
    # Instrumented hot async methods (#1258)
    # -------------------------------------------------------------------

    async def aput(self, *args: Any, **kwargs: Any) -> Any:
        if _checkpoint_op_bucket.get() is None:
            return await self._saver.aput(*args, **kwargs)
        start = time.perf_counter()
        try:
            return await self._saver.aput(*args, **kwargs)
        finally:
            _record("aput", (time.perf_counter() - start) * 1000.0)

    async def aget(self, *args: Any, **kwargs: Any) -> Any:
        if _checkpoint_op_bucket.get() is None:
            return await self._saver.aget(*args, **kwargs)
        start = time.perf_counter()
        try:
            return await self._saver.aget(*args, **kwargs)
        finally:
            _record("aget", (time.perf_counter() - start) * 1000.0)

    async def aput_writes(self, *args: Any, **kwargs: Any) -> Any:
        if _checkpoint_op_bucket.get() is None:
            return await self._saver.aput_writes(*args, **kwargs)
        start = time.perf_counter()
        try:
            return await self._saver.aput_writes(*args, **kwargs)
        finally:
            _record("aput_writes", (time.perf_counter() - start) * 1000.0)

    async def aget_tuple(self, *args: Any, **kwargs: Any) -> Any:
        if _checkpoint_op_bucket.get() is None:
            return await self._saver.aget_tuple(*args, **kwargs)
        start = time.perf_counter()
        try:
            return await self._saver.aget_tuple(*args, **kwargs)
        finally:
            _record("aget_tuple", (time.perf_counter() - start) * 1000.0)

    # -------------------------------------------------------------------
    # Pass-through delegations (BaseCheckpointSaver surface)
    # -------------------------------------------------------------------

    @property
    def config_specs(self) -> list[Any]:
        return self._saver.config_specs

    # Sync API
    def get(self, config: Any) -> Any:
        return self._saver.get(config)

    def get_tuple(self, config: Any) -> Any:
        return self._saver.get_tuple(config)

    def list(
        self,
        config: Any,
        *,
        filter: dict[str, Any] | None = None,
        before: Any = None,
        limit: int | None = None,
    ) -> Iterator[Any]:
        return self._saver.list(config, filter=filter, before=before, limit=limit)

    def put(self, *args: Any, **kwargs: Any) -> Any:
        return self._saver.put(*args, **kwargs)

    def put_writes(self, *args: Any, **kwargs: Any) -> Any:
        return self._saver.put_writes(*args, **kwargs)

    def delete_thread(self, thread_id: str) -> None:
        return self._saver.delete_thread(thread_id)

    def delete_for_runs(self, run_ids: Sequence[str]) -> None:
        return self._saver.delete_for_runs(run_ids)

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        return self._saver.copy_thread(source_thread_id, target_thread_id)

    def prune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        return self._saver.prune(thread_ids, strategy=strategy)

    # Async API (non-instrumented)
    async def alist(
        self,
        config: Any,
        *,
        filter: dict[str, Any] | None = None,
        before: Any = None,
        limit: int | None = None,
    ) -> AsyncIterator[Any]:
        async for item in self._saver.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        return await self._saver.adelete_thread(thread_id)

    async def adelete_for_runs(self, run_ids: Sequence[str]) -> None:
        return await self._saver.adelete_for_runs(run_ids)

    async def acopy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        return await self._saver.acopy_thread(source_thread_id, target_thread_id)

    async def aprune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        return await self._saver.aprune(thread_ids, strategy=strategy)

    # Versioning / allowlist
    def get_next_version(self, current: Any, channel: Any = None) -> Any:
        return self._saver.get_next_version(current, channel)

    def with_allowlist(
        self, extra_allowlist: Collection[tuple[str, ...]]
    ) -> BaseCheckpointSaver[Any]:
        new_saver = self._saver.with_allowlist(extra_allowlist)
        if new_saver is self._saver:
            return self
        return InstrumentedCheckpointer(new_saver)


def create_redis_checkpointer(
    redis_url: str,
    *,
    ttl_minutes: int | None = None,
    refresh_on_read: bool = True,
) -> InstrumentedCheckpointer:
    """Create AsyncRedisSaver for persistent conversation memory (SDK).

    Returns an :class:`InstrumentedCheckpointer` wrapping the SDK saver so
    callers can opt into direct checkpoint overhead measurement (#1258) via
    :func:`begin_checkpoint_overhead_capture` /
    :func:`end_checkpoint_overhead_capture`. The wrapper subclasses
    :class:`BaseCheckpointSaver` (#2147) so LangGraph's
    ``ensure_valid_checkpointer`` accepts it; all other behaviour is
    identical to the underlying SDK saver.

    Args:
        redis_url: Redis connection string.
        ttl_minutes: Checkpoint TTL in minutes. None = no expiry.
        refresh_on_read: Sliding expiration for active threads.

    Caller must: ``await checkpointer.asetup()`` before use.
    """
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    kwargs: dict[str, Any] = {"redis_url": redis_url}
    if ttl_minutes is not None:
        kwargs["ttl"] = {
            "default_ttl": ttl_minutes,
            "refresh_on_read": refresh_on_read,
        }

    logger.info(
        "Creating AsyncRedisSaver (ttl_minutes=%s, refresh_on_read=%s)",
        ttl_minutes,
        refresh_on_read,
    )
    return InstrumentedCheckpointer(AsyncRedisSaver(**kwargs))


def create_fallback_checkpointer() -> MemorySaver:
    """In-memory checkpointer for dev/testing."""
    logger.info("Using MemorySaver (in-memory, non-persistent)")
    return MemorySaver()


# Backward compat: default singleton for dev/tests
checkpointer = MemorySaver()
