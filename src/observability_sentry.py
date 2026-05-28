"""Sentry-compatible error tracking initialization (#2060).

Drop-in helper that boots ``sentry-sdk`` for the bot/RAG runtime when a
Sentry-compatible DSN (Bugsink self-host or Sentry Cloud) is configured. The
helper is intentionally tiny and SDK-native:

- ``send_default_pii=False`` is hard-coded (cannot be turned on via env).
- ``EventScrubber`` reuses the SDK's ``DEFAULT_DENYLIST`` and adds the
  project's secret keys (Telegram/Kommo/LiteLLM/Langfuse/etc.).
- ``before_send`` runs every event payload through the project
  :class:`~src.security.pii_redaction.PIIRedactor` so Telegram user IDs,
  phone numbers, emails, Ukrainian passport / РНОКПП IDs and any over-long
  free-text strings are masked before leaving the process.
- When ``SENTRY_DSN`` is unset or blank, the helper logs a single info-level
  skip line and returns ``False`` — the bot starts cleanly without any
  Sentry-compatible backend.

See ``docs/observability/bugsink-setup.md`` for the operator-facing
configuration contract and the umbrella issue
`#1417 <https://github.com/yastman/rag/issues/1417>`_ for context.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import metadata as _metadata
from typing import Any

import sentry_sdk
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

from src.security.pii_redaction import PIIRedactor


__all__ = [
    "_reset_for_tests",
    "add_safe_breadcrumb",
    "error_boundary_breadcrumb",
    "handler_breadcrumb",
    "hash_id",
    "initialize_sentry",
    "lifecycle_breadcrumb",
    "message_receive_breadcrumb",
    "rag_breadcrumb",
    "runtime_scope",
    "session_breadcrumb",
    "set_runtime_tags",
]


logger = logging.getLogger(__name__)

# Indirection seams so tests can patch the SDK call without touching the
# global ``sentry_sdk`` module (which other helpers may import).
_sentry_init = sentry_sdk.init
_sentry_capture_message = sentry_sdk.capture_message
_sentry_add_breadcrumb = sentry_sdk.add_breadcrumb
_sentry_set_tag = sentry_sdk.set_tag
_sentry_new_scope = sentry_sdk.new_scope

_PII_TRUNCATE_LIMIT = 4000

# Project-specific keys that must be scrubbed in addition to sentry-sdk's
# DEFAULT_DENYLIST (which already covers ``password``, ``secret``, ``api_key``,
# etc.). EventScrubber matches these case-insensitively against event field
# names.
_PROJECT_DENYLIST: tuple[str, ...] = (
    "telegram_bot_token",
    "bot_token",
    "telegram_token",
    "kommo_token",
    "kommo_jwt",
    "kommo_client_secret",
    "litellm_master_key",
    "langfuse_secret_key",
    "langfuse_public_key",
    "openai_api_key",
    "anthropic_api_key",
    "groq_api_key",
    "voyage_api_key",
    "redis_password",
    "postgres_password",
    "clickhouse_password",
    "minio_root_password",
)

_redactor = PIIRedactor()
_initialized = False
_skip_logged = False


def _resolve(value: str | None, env_name: str, default: str | None = None) -> str | None:
    """Return *value* when set, else env var, else default. Strips whitespace."""
    candidate = value if value is not None else os.getenv(env_name, "")
    candidate = (candidate or "").strip()
    if candidate:
        return candidate
    return default


def _resolve_dsn(explicit: str | None) -> str | None:
    """Return a non-blank DSN or ``None``."""
    candidate = explicit if explicit is not None else os.getenv("SENTRY_DSN", "")
    candidate = (candidate or "").strip()
    return candidate or None


def _resolve_traces_sample_rate(explicit: float | None) -> float:
    if explicit is not None:
        return float(explicit)
    raw = (os.getenv("SENTRY_TRACES_SAMPLE_RATE", "") or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid SENTRY_TRACES_SAMPLE_RATE=%r — falling back to 0.0", raw)
        return 0.0


def _resolve_release(explicit: str | None) -> str:
    candidate = explicit if explicit is not None else os.getenv("SENTRY_RELEASE", "")
    candidate = (candidate or "").strip()
    if candidate:
        return candidate
    # Fall back to the installed package version so Bugsink/Sentry can group
    # events by release without operator-side configuration.
    try:
        return f"contextual-rag@{_metadata.version('contextual-rag')}"
    except _metadata.PackageNotFoundError:
        return "contextual-rag@unknown"


def _resolve_environment(explicit: str | None) -> str:
    candidate = explicit if explicit is not None else os.getenv("SENTRY_ENVIRONMENT", "")
    candidate = (candidate or "").strip()
    return candidate or "local"


def _resolve_debug(explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = (os.getenv("SENTRY_DEBUG", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _make_event_scrubber() -> EventScrubber:
    """Return an EventScrubber that extends the SDK default denylist."""
    denylist = list(DEFAULT_DENYLIST) + list(_PROJECT_DENYLIST)
    return EventScrubber(denylist=denylist)


def _redact(value: Any) -> Any:
    """Mask + truncate a value via PIIRedactor (str | dict | list)."""
    return _redactor.mask(value, max_length=_PII_TRUNCATE_LIMIT)


def _redact_in_place(event: dict[str, Any], key: str) -> None:
    if key in event:
        event[key] = _redact(event[key])


def _redact_logentry(event: dict[str, Any]) -> None:
    logentry = event.get("logentry")
    if isinstance(logentry, dict) and "message" in logentry:
        logentry["message"] = _redact(logentry["message"])


def _redact_request(event: dict[str, Any]) -> None:
    request = event.get("request")
    if not isinstance(request, dict):
        return
    for key in ("data", "query_string", "headers", "cookies"):
        if key in request:
            request[key] = _redact(request[key])


def _redact_breadcrumbs(event: dict[str, Any]) -> None:
    breadcrumbs = event.get("breadcrumbs")
    if not isinstance(breadcrumbs, dict):
        return
    values = breadcrumbs.get("values")
    if not isinstance(values, list):
        return
    for crumb in values:
        if not isinstance(crumb, dict):
            continue
        for key in ("message", "data"):
            if key in crumb:
                crumb[key] = _redact(crumb[key])


def _get_langfuse_client() -> Any | None:
    """Return the active Langfuse v4 client or ``None``.

    Tolerates missing Langfuse SDK (e.g. minimal CI envs without the optional
    extra) and uninitialised clients. Used by ``_make_before_send`` to attach
    the active trace ID to every Sentry event so on-call can pivot from a
    Sentry incident → Langfuse trace → Loki logs in one click (#2218).
    """
    try:
        from langfuse import get_client
    except ImportError:
        return None
    try:
        return get_client()
    except Exception:
        # Langfuse may raise when no client has been initialised yet — that
        # is the documented v4 SDK behaviour. Treat it as "no active trace".
        return None


def _attach_langfuse_trace_to_event(event: dict[str, Any]) -> None:
    """Attach the active Langfuse trace_id / observation_id to a Sentry event.

    SDK-native: reads ``langfuse.get_client().get_current_trace_id()`` (v4)
    which returns the OTEL trace ID for the active ``@observe`` context.
    The Langfuse SDK runs on top of OpenTelemetry, so this trace_id matches
    the one ``otelTraceID`` is injected into structured logs (Epic G #2217)
    and the one ``traceparent`` carries across HTTP boundaries (Epic O+P).

    Result: Sentry UI shows a clickable ``langfuse_trace_id`` tag on every
    captured event + a ``langfuse`` context block with a deep-link URL.

    Failures are swallowed: a broken Langfuse SDK must NEVER block a Sentry
    event from being captured.
    """
    try:
        client = _get_langfuse_client()
        if client is None:
            return
        trace_id = client.get_current_trace_id()
        if not trace_id:
            return

        observation_id = client.get_current_observation_id()

        tags = event.setdefault("tags", {})
        if isinstance(tags, dict):
            tags["langfuse_trace_id"] = trace_id

        contexts = event.setdefault("contexts", {})
        if isinstance(contexts, dict):
            langfuse_ctx: dict[str, str] = {"trace_id": trace_id}
            if observation_id:
                langfuse_ctx["observation_id"] = observation_id
            host = (os.getenv("LANGFUSE_HOST", "") or "").strip().rstrip("/")
            if host:
                langfuse_ctx["url"] = f"{host}/trace/{trace_id}"
            contexts["langfuse"] = langfuse_ctx
    except Exception:
        # Cross-link is a best-effort enrichment; never let it kill the event.
        logger.debug("Sentry <-> Langfuse cross-link failed", exc_info=True)


def _make_before_send():
    """Return a ``before_send`` callable that masks PII before egress.

    Two-stage hook:

    1. PII redaction (existing — unchanged).
    2. Langfuse trace cross-link enrichment (#2218): attaches
       ``langfuse_trace_id`` tag + ``langfuse`` context block when an
       ``@observe`` span is active. Runs after PII scrub so the trace IDs
       (which are 16-char hex, never PII) are not accidentally masked.
    """

    def before_send(event: dict[str, Any], hint: Any | None = None) -> dict[str, Any] | None:
        try:
            _redact_in_place(event, "message")
            _redact_logentry(event)
            _redact_in_place(event, "extra")
            _redact_in_place(event, "tags")
            _redact_in_place(event, "contexts")
            _redact_request(event)
            _redact_breadcrumbs(event)
        except Exception:
            logger.warning("Sentry before_send PII scrub failed", exc_info=True)
        _attach_langfuse_trace_to_event(event)
        return event

    return before_send


def initialize_sentry(
    *,
    dsn: str | None = None,
    environment: str | None = None,
    release: str | None = None,
    traces_sample_rate: float | None = None,
    debug: bool | None = None,
    force: bool = False,
) -> bool:
    """Boot ``sentry-sdk`` if a DSN is configured.

    Returns ``True`` when the SDK was initialized, ``False`` otherwise (no
    DSN, blank DSN, or already initialized without ``force``).

    The helper is idempotent: a second call is a no-op unless ``force=True``.
    Explicit keyword arguments override the matching ``SENTRY_*`` env vars.
    """
    global _initialized, _skip_logged

    if _initialized and not force:
        return True

    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn:
        if not _skip_logged:
            logger.info("Sentry error tracking disabled: SENTRY_DSN is unset or blank")
            _skip_logged = True
        return False

    init_kwargs: dict[str, Any] = {
        "dsn": resolved_dsn,
        "environment": _resolve_environment(environment),
        "release": _resolve_release(release),
        "traces_sample_rate": _resolve_traces_sample_rate(traces_sample_rate),
        # Hard-coded safety knobs:
        "send_default_pii": False,
        "event_scrubber": _make_event_scrubber(),
        "before_send": _make_before_send(),
        "debug": _resolve_debug(debug),
        "max_breadcrumbs": 50,
    }

    try:
        _sentry_init(**init_kwargs)
    except Exception:
        logger.warning("Failed to initialize sentry-sdk", exc_info=True)
        return False

    _initialized = True
    logger.info(
        "Sentry initialized (environment=%s, release=%s, traces_sample_rate=%s)",
        init_kwargs["environment"],
        init_kwargs["release"],
        init_kwargs["traces_sample_rate"],
    )
    return True


def _reset_for_tests() -> None:
    """Test-only: reset module state so initialize_sentry can be re-driven."""
    global _initialized, _skip_logged
    _initialized = False
    _skip_logged = False


# ---------------------------------------------------------------------------
# Runtime tags + trace context (#2061)
# ---------------------------------------------------------------------------


_HASH_PREFIX_LEN = 16


def hash_id(value: str | int) -> str:
    """Return a stable, opaque 16-char hex hash of an ID.

    Used for ``chat_id_hash`` / ``telegram_user_id_hash`` Sentry tags so we
    keep the ability to correlate events for the same user without leaking
    the raw Telegram identifier. Inputs are normalised to ``str`` so
    ``hash_id(123)`` and ``hash_id("123")`` collide as expected.
    """
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return digest[:_HASH_PREFIX_LEN]


def set_runtime_tags(
    *,
    service: str = "telegram-bot",
    component: str | None = None,
    pipeline_mode: str | None = None,
    route: str | None = None,
    extra_tags: dict[str, str] | None = None,
) -> None:
    """Set static service-level tags on the active Sentry isolation scope.

    Intended to be called once at startup (after :func:`initialize_sentry`)
    so every event picks up the service / component / pipeline_mode / route
    metadata. ``extra_tags`` is an escape hatch for deployment-specific
    labels (locale, tenant, etc.).
    """
    _sentry_set_tag("service", service)
    if component is not None:
        _sentry_set_tag("component", component)
    if pipeline_mode is not None:
        _sentry_set_tag("pipeline_mode", pipeline_mode)
    if route is not None:
        _sentry_set_tag("route", route)
    for key, value in (extra_tags or {}).items():
        _sentry_set_tag(key, value)


@contextmanager
def runtime_scope(
    *,
    chat_id: str | int | None = None,
    telegram_user_id: str | int | None = None,
    trace_id: str | None = None,
    langfuse_trace_id: str | None = None,
    route: str | None = None,
    pipeline_mode: str | None = None,
    extra_tags: dict[str, str] | None = None,
) -> Iterator[Any]:
    """Push a request-scoped Sentry scope with PII-safe runtime metadata.

    The context manager emits hashed ``chat_id_hash`` and
    ``telegram_user_id_hash`` tags and a ``trace`` context block that
    correlates the current Telegram update with its Langfuse / OTEL trace.
    Raw Telegram identifiers and free-text payloads never reach the SDK.

    All arguments are optional — ``None`` values are silently skipped so
    callers can call ``runtime_scope(chat_id=update.chat.id, ...)`` without
    branching on availability.
    """
    with _sentry_new_scope() as scope:
        if chat_id is not None:
            scope.set_tag("chat_id_hash", hash_id(chat_id))
        if telegram_user_id is not None:
            scope.set_tag("telegram_user_id_hash", hash_id(telegram_user_id))

        trace_block: dict[str, str] = {}
        if trace_id is not None:
            scope.set_tag("trace_id", trace_id)
            trace_block["trace_id"] = trace_id
        if langfuse_trace_id is not None:
            scope.set_tag("langfuse_trace_id", langfuse_trace_id)
            trace_block["langfuse_trace_id"] = langfuse_trace_id
        if trace_block:
            scope.set_context("trace", trace_block)

        if route is not None:
            scope.set_tag("route", route)
        if pipeline_mode is not None:
            scope.set_tag("pipeline_mode", pipeline_mode)
        for key, value in (extra_tags or {}).items():
            scope.set_tag(key, value)

        yield scope


# ---------------------------------------------------------------------------
# PII-safe breadcrumbs (#2062)
# ---------------------------------------------------------------------------


# Allow-list of safe metadata keys that ``message_receive_breadcrumb`` is
# permitted to forward. Anything outside this set (raw text, tokens, CRM
# payloads, headers, etc.) is dropped at the source — the ``before_send``
# scrubber from #2060 acts as a second line of defence.
_MESSAGE_RECEIVE_SAFE_KEYS: frozenset[str] = frozenset(
    {
        "content_type",
        "text_length",
        "voice_seconds",
        "chat_id_hash",
        "telegram_user_id_hash",
        "route",
        "pipeline_mode",
        "trace_id",
        "langfuse_trace_id",
    }
)


def add_safe_breadcrumb(
    *,
    category: str,
    message: str | None = None,
    data: dict[str, Any] | None = None,
    level: str = "info",
) -> None:
    """Add a Sentry breadcrumb whose ``message`` and ``data`` are PII-redacted.

    Drop-in replacement for ``sentry_sdk.add_breadcrumb`` — runs every
    string field through :class:`~src.security.pii_redaction.PIIRedactor`
    (mask + truncate at 4000 chars) before delegating to the SDK. If
    redaction itself fails, the breadcrumb is silently dropped rather than
    risking a partially-redacted payload reaching Sentry.
    """
    try:
        safe_message = _redact(message) if message is not None else None
        safe_data = _redact(data) if data is not None else None
    except Exception:
        logger.warning("Sentry breadcrumb PII scrub failed; dropping breadcrumb", exc_info=True)
        return

    _sentry_add_breadcrumb(
        category=category,
        message=safe_message,
        data=safe_data,
        level=level,
    )


def lifecycle_breadcrumb(event: str, **data: Any) -> None:
    """Bot/RAG lifecycle event (startup, shutdown, config reload)."""
    add_safe_breadcrumb(
        category="lifecycle",
        message=event,
        data=dict(data) if data else None,
    )


def rag_breadcrumb(event: str, *, level: str = "info", **data: Any) -> None:
    """RAG pipeline lifecycle (rag.start, rag.end, rag.fallback)."""
    add_safe_breadcrumb(
        category="rag",
        message=event,
        data=dict(data) if data else None,
        level=level,
    )


def session_breadcrumb(event: str, **data: Any) -> None:
    """Conversation/session lifecycle (session.create, session.destroy)."""
    add_safe_breadcrumb(
        category="session",
        message=event,
        data=dict(data) if data else None,
    )


def handler_breadcrumb(event: str, **data: Any) -> None:
    """Telegram handler dispatch (handler.dispatch, handler.exit)."""
    add_safe_breadcrumb(
        category="handler",
        message=event,
        data=dict(data) if data else None,
    )


def error_boundary_breadcrumb(event: str, **data: Any) -> None:
    """Caught-exception boundary marker — emitted at warning level."""
    add_safe_breadcrumb(
        category="error_boundary",
        message=event,
        data=dict(data) if data else None,
        level="warning",
    )


def message_receive_breadcrumb(**data: Any) -> None:
    """Telegram message receipt — strict allow-list, NEVER logs raw text.

    Only the ``_MESSAGE_RECEIVE_SAFE_KEYS`` metadata keys are forwarded to
    the breadcrumb payload. Raw message text, tokens, CRM payloads, and any
    other key that might leak PII are dropped at the source.
    """
    safe_data = {k: v for k, v in data.items() if k in _MESSAGE_RECEIVE_SAFE_KEYS}
    add_safe_breadcrumb(
        category="message_receive",
        message=None,
        data=safe_data or None,
    )
