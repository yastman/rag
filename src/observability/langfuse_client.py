"""Langfuse observability helpers with runtime initialization.

This module always exposes the real Langfuse SDK APIs (`observe`, `get_client`,
`propagate_attributes`) and relies on SDK-native graceful degradation when
credentials are unavailable.

Use `initialize_langfuse()` after loading runtime config (e.g. BotConfig) to
ensure credentials from `.env`/environment are applied before first tracing.

Split structure:
- langfuse_init.py        — initialization, OTEL wiring, config resolution
- langfuse_model_sync.py  — model definition sync
- langfuse_client.py      — SDK re-exports, PII masking, client access, lifecycle helpers
"""

import contextlib
import logging
import warnings
from typing import Any

from src.observability.langfuse_init import (
    _reset_langfuse_init_state,
    get_langfuse_init_client,
)
from src.observability.langfuse_init import (
    initialize_langfuse as _init_langfuse,
)
from src.security.pii_redaction import PIIRedactor


logger = logging.getLogger(__name__)

_MAX_PII_TEXT_LENGTH = 4000

_pii_redactor = PIIRedactor()

# ---------------------------------------------------------------------------
# Issue #1381 — suppress the Langfuse SDK Pydantic V1 UserWarning
# ---------------------------------------------------------------------------


def _install_langfuse_warning_filters() -> None:
    """Suppress the Langfuse Pydantic V1 ``UserWarning`` on Python 3.14+."""
    warnings.filterwarnings(
        "ignore",
        message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14.*",
        category=UserWarning,
    )


_install_langfuse_warning_filters()

# ---------------------------------------------------------------------------
# Guarded Langfuse SDK import (graceful degradation under Python 3.14)
# ---------------------------------------------------------------------------

try:
    from langfuse import Langfuse
    from langfuse import get_client as _real_get_client
    from langfuse import observe as _real_observe
    from langfuse import propagate_attributes as _real_propagate

    _LANGFUSE_AVAILABLE = True
    _LANGFUSE_IMPORT_ERROR = None
except Exception as _e:
    _LANGFUSE_AVAILABLE = False
    _LANGFUSE_IMPORT_ERROR = _e

    class Langfuse:  # type: ignore[no-redef]
        """Placeholder that raises the original import error on instantiation."""

        def __init__(self, *args, **kwargs):
            raise _LANGFUSE_IMPORT_ERROR

    def _real_observe(
        *args, **kwargs
    ):  # dead-code-false-positive — assigned to `observe` public export at module level (observe = _real_observe)
        """No-op decorator factory."""

        def decorator(func):
            return func

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

    def _real_get_client():  # type: ignore[misc]
        return None

    @contextlib.contextmanager
    def _real_propagate(**kwargs):  # type: ignore[misc]
        yield


# ---------------------------------------------------------------------------
# Public SDK exports
# ---------------------------------------------------------------------------

observe = _real_observe
get_client = _real_get_client
propagate_attributes = _real_propagate


# ---------------------------------------------------------------------------
# PII masking (always available)
# ---------------------------------------------------------------------------


def mask_pii(data: Any) -> Any:
    """Mask PII before sending to Langfuse."""
    return _pii_redactor.mask(data, max_length=_MAX_PII_TEXT_LENGTH)


# ---------------------------------------------------------------------------
# Initialization — delegate to langfuse_init, injecting Langfuse class + mask
# ---------------------------------------------------------------------------


def initialize_langfuse(
    *,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    force: bool = False,
) -> Langfuse | None:
    """Initialize a Langfuse client after runtime config is loaded.

    Returns None when credentials are missing, endpoint unreachable, or client creation fails.
    When the endpoint is unreachable, logs a WARNING once and skips OTEL exporter registration.

    Thread-safe (#2214): initialization is serialized by ``_langfuse_init_lock``
    so concurrent startup threads cannot each build a client and
    double-register the atexit shutdown hook (the second client would
    overwrite the global and the first would never flush).
    """
    return _init_langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        force=force,
        _langfuse_cls=Langfuse if _LANGFUSE_AVAILABLE else None,
        _mask_fn=mask_pii,
    )


def get_langfuse_client() -> Langfuse | None:
    """Get initialized Langfuse client, lazy-initializing from env when possible."""
    client = get_langfuse_init_client()
    if client is not None:
        return client
    return initialize_langfuse()


def flush_langfuse() -> None:
    """Flush buffered spans/scores on the initialized client, if one exists.

    #2214: the ``BatchSpanProcessor`` flushes on a clean ``atexit``, but a hard
    ``os._exit()`` or a signal kill drops whatever is still buffered. Long-lived
    CLI entry points (e.g. ingestion) should call this in a ``finally`` block so
    their lifecycle traces are not silently lost on abrupt shutdown.

    This is a no-op when no client has been initialized (so it never triggers a
    lazy init just to flush) and swallows flush errors — losing observability on
    shutdown must never crash the caller.
    """
    client = get_langfuse_init_client()
    if client is None:
        return
    with contextlib.suppress(Exception):
        client.flush()


def _reset_langfuse_client_for_tests() -> None:
    """Reset module-level client cache (test-only helper)."""
    _reset_langfuse_init_state()


# ---------------------------------------------------------------------------
# Lifecycle trace helpers (shared by voice and ingestion families)
# ---------------------------------------------------------------------------


def traced_pipeline(  # dead-code-false-positive — called via telegram_bot/observability.py and src/observability/__init__.py re-exports; used in tests/smoke/test_langgraph_smoke.py
    *,
    session_id: str,
    user_id: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Context manager for pipeline-level trace propagation.

    Wraps propagate_attributes with sensible defaults.
    Use at any entry point that invokes @observe-decorated functions.
    """
    return propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=tags or [],
        metadata=metadata or {},
    )


def make_lifecycle_session_id(family: str, key: str) -> str:
    """Build a stable trace session id for a lifecycle family.

    Returns ``"{family}-{normalized_key}"`` or ``"{family}-unknown"`` when *key*
    is empty or whitespace-only.
    """
    normalized = (key or "").strip().replace(" ", "-")
    return f"{family}-{normalized or 'unknown'}"


def update_lifecycle_trace(
    *,
    family: str,
    span_name: str,
    session_id: str,
    user_id: str,
    tags: list[str],
    metadata: dict[str, Any],
    trace_id: str | None = None,
) -> None:
    """Update (or create) a lifecycle trace span via Langfuse.

    This is the shared core used by both the voice and ingestion families.
    It creates a span observation and propagates trace attributes in a single
    context block.
    """
    lf = get_langfuse_client()
    if lf is None:
        return

    resolved_trace_id = trace_id or lf.create_trace_id(seed=session_id)

    with (
        lf.start_as_current_observation(
            as_type="span",
            name=span_name,
            trace_context={"trace_id": resolved_trace_id},
        ) as observation,
        propagate_attributes(
            session_id=session_id,
            user_id=user_id,
            tags=tags,
        ),
    ):
        observation.update(metadata=metadata)


async def try_update_lifecycle_trace_async(
    *,
    family: str,
    span_name: str,
    session_id: str,
    user_id: str,
    tags: list[str],
    metadata: dict[str, Any],
    trace_id: str | None = None,
) -> None:
    """Best-effort async wrapper around :func:`update_lifecycle_trace`.

    Suppresses all exceptions so callers never fail due to tracing issues.
    """
    with contextlib.suppress(Exception):
        update_lifecycle_trace(
            family=family,
            span_name=span_name,
            session_id=session_id,
            user_id=user_id,
            tags=tags,
            metadata=metadata,
            trace_id=trace_id,
        )


def create_callback_handler(
    *,
    trace_context: Any | None = None,
) -> Any | None:
    """Create a native v4 Langfuse CallbackHandler for LangChain integrations.

    Centralises the ``langfuse.langchain`` import so callers outside
    ``src.observability`` never import from the ``langfuse`` package directly.

    Returns None when Langfuse is not configured or handler init fails.
    """
    if not _LANGFUSE_AVAILABLE:
        return None
    if get_langfuse_client() is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(trace_context=trace_context)
    except Exception:
        logger.warning("Failed to create Langfuse CallbackHandler", exc_info=True)
        return None


def get_score_config_types() -> tuple[Any, Any] | None:
    """Return (ConfigCategory, ScoreConfigDataType) from the Langfuse SDK.

    Centralises deep API type imports so callers outside ``src.observability``
    never import from the ``langfuse`` package directly.

    Returns None when Langfuse is not available.
    """
    if not _LANGFUSE_AVAILABLE:
        return None
    try:
        from langfuse.api.commons.types.config_category import ConfigCategory
        from langfuse.api.commons.types.score_config_data_type import (
            ScoreConfigDataType,
        )

        return ConfigCategory, ScoreConfigDataType
    except Exception:
        logger.warning("Langfuse score config types unavailable", exc_info=True)
        return None
