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

import logging
import os
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
    "initialize_sentry",
    "lifecycle_breadcrumb",
    "message_receive_breadcrumb",
    "rag_breadcrumb",
    "session_breadcrumb",
]


logger = logging.getLogger(__name__)

# Indirection seams so tests can patch the SDK call without touching the
# global ``sentry_sdk`` module (which other helpers may import).
_sentry_init = sentry_sdk.init
_sentry_capture_message = sentry_sdk.capture_message
_sentry_add_breadcrumb = sentry_sdk.add_breadcrumb

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
    return _resolve(explicit, "SENTRY_DSN")


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
    explicit_value = _resolve(explicit, "SENTRY_RELEASE")
    if explicit_value:
        return explicit_value
    # Fall back to the installed package version so Bugsink/Sentry can group
    # events by release without operator-side configuration.
    try:
        return f"contextual-rag@{_metadata.version('contextual-rag')}"
    except _metadata.PackageNotFoundError:
        return "contextual-rag@unknown"


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


def _make_before_send():
    """Return a ``before_send`` callable that masks PII before egress."""

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
        "environment": _resolve(environment, "SENTRY_ENVIRONMENT", default="local"),
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
