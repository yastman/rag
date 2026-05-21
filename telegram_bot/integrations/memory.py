"""Checkpointer factory for LangGraph conversation persistence.

Uses AsyncRedisSaver (langgraph-checkpoint-redis SDK) when Redis URL is configured.
Falls back to MemorySaver for dev/testing. Zero custom logic — SDK wiring only.

Direct checkpoint overhead measurement (***REMOVED***1258)
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
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any

from langgraph.checkpoint.memory import MemorySaver


logger = logging.getLogger(__name__)


***REMOVED*** -----------------------------------------------------------------------------
***REMOVED*** Direct checkpointer overhead measurement (***REMOVED***1258)
***REMOVED*** -----------------------------------------------------------------------------

***REMOVED***: Per-invoke bucket of checkpoint operation durations and call count.
***REMOVED***: ``None`` means capture is not active (operations pass through untimed).
_checkpoint_op_bucket: ContextVar[dict[str, float] | None] = ContextVar(
    "checkpoint_op_bucket", default=None
)

***REMOVED***: Methods we measure on the wrapped checkpointer. These are the four async
***REMOVED***: I/O entry points exposed by every LangGraph saver implementation; together
***REMOVED***: they account for all per-invoke checkpoint reads and writes.
_INSTRUMENTED_METHODS: tuple[str, ...] = (
    "aput",
    "aget",
    "aput_writes",
    "aget_tuple",
)


def begin_checkpoint_overhead_capture() -> dict[str, float]:
    """Start a per-invoke direct measurement of checkpoint I/O latency (***REMOVED***1258).

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


class InstrumentedCheckpointer:
    """Time the four hot checkpoint methods and accumulate durations (***REMOVED***1258).

    Delegates everything else to the underlying saver via ``__getattr__``.
    The wrapper is transparent: LangGraph sees the same interface and treats
    it identically. Capture is gated by the ``_checkpoint_op_bucket``
    ContextVar so concurrent ``ainvoke`` calls in the same event loop each
    accumulate into their own bucket without cross-talk.
    """

    __slots__ = ("_saver",)

    def __init__(self, saver: Any) -> None:
        object.__setattr__(self, "_saver", saver)

    def __repr__(self) -> str:  ***REMOVED*** pragma: no cover — debug only
        return f"InstrumentedCheckpointer({self._saver!r})"

    def __getattr__(self, name: str) -> Any:
        ***REMOVED*** __getattr__ runs only when normal lookup misses (i.e. for any
        ***REMOVED*** attribute that's not on InstrumentedCheckpointer itself).
        attr = getattr(self._saver, name)
        if name in _INSTRUMENTED_METHODS:
            return self._wrap_async(name, attr)
        return attr

    @staticmethod
    def _record(name: str, elapsed_ms: float) -> None:
        bucket = _checkpoint_op_bucket.get()
        if bucket is None:
            return
        bucket[f"{name}_ms"] = bucket.get(f"{name}_ms", 0.0) + elapsed_ms
        bucket["calls"] = bucket.get("calls", 0.0) + 1.0

    def _wrap_async(self, name: str, fn: Any) -> Any:
        async def _instrumented(*args: Any, **kwargs: Any) -> Any:
            ***REMOVED*** Fast path: capture is off, skip timing entirely.
            if _checkpoint_op_bucket.get() is None:
                return await fn(*args, **kwargs)
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                ***REMOVED*** _record is fail-soft: if anything goes wrong (bucket
                ***REMOVED*** mutated by another task etc.) instrumentation must NEVER
                ***REMOVED*** break the underlying call.
                try:
                    InstrumentedCheckpointer._record(name, elapsed_ms)
                except Exception:
                    logger.debug(
                        "InstrumentedCheckpointer._record failed for %s",
                        name,
                        exc_info=True,
                    )

        _instrumented.__name__ = name
        return _instrumented


def create_redis_checkpointer(
    redis_url: str,
    *,
    ttl_minutes: int | None = None,
    refresh_on_read: bool = True,
) -> Any:
    """Create AsyncRedisSaver for persistent conversation memory (SDK).

    Returns an :class:`InstrumentedCheckpointer` wrapping the SDK saver so
    callers can opt into direct checkpoint overhead measurement (***REMOVED***1258) via
    :func:`begin_checkpoint_overhead_capture` /
    :func:`end_checkpoint_overhead_capture`. The wrapper is transparent — its
    other behaviour is identical to the underlying SDK saver.

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


***REMOVED*** Backward compat: default singleton for dev/tests
checkpointer = MemorySaver()
