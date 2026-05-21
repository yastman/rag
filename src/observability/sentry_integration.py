"""Sentry SDK integration with PII filtering for the RAG bot."""

from __future__ import annotations

import logging
from typing import Any

import sentry_sdk

from src.security.pii_redaction import PIIRedactor


logger = logging.getLogger(__name__)

_redactor = PIIRedactor()

# Keys whose values must never be sent to Sentry.
_BLOCKED_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "query",
        "raw_query",
        "answer_text",
        "phone",
        "email",
        "token",
        "password",
        "secret",
        "api_key",
    }
)


def initialize_sentry(
    *,
    dsn: str,
    environment: str,
    release: str,
    traces_sample_rate: float,
    service_name: str = "telegram-bot",
) -> None:
    """Initialize Sentry SDK if DSN is provided.

    When *dsn* is empty the call is a no-op and no network requests are made.
    """
    if not dsn or not isinstance(dsn, str) or not dsn.strip():
        logger.info("Sentry disabled (SENTRY_DSN is empty)")
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        traces_sample_rate=traces_sample_rate,
        before_send=_filter_pii,
        before_breadcrumb=_filter_breadcrumb_pii,
        server_name=service_name,
    )
    logger.info("Sentry initialized (env=%s, service=%s)", environment, service_name)


def _scrub_value(value: Any) -> Any:
    """Recursively scrub PII from a value using PIIRedactor."""
    if isinstance(value, str):
        return _redactor.mask(value)
    if isinstance(value, dict):
        return _scrub_dict(value)
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


def _scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Scrub PII from dict, removing blocked keys entirely."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key in _BLOCKED_KEYS:
            result[key] = "[REDACTED]"
        else:
            result[key] = _scrub_value(value)
    return result


def _filter_pii(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Sentry before_send hook: strip PII from events."""
    # Scrub top-level message
    if "message" in event and isinstance(event["message"], str):
        event["message"] = _redactor.mask(event["message"])

    # Scrub extra data
    if "extra" in event and isinstance(event["extra"], dict):
        event["extra"] = _scrub_dict(event["extra"])

    # Scrub breadcrumbs
    if "breadcrumbs" in event and isinstance(event["breadcrumbs"], dict):
        values = event["breadcrumbs"].get("values", [])
        event["breadcrumbs"]["values"] = [_scrub_breadcrumb(bc) for bc in values]

    return event


def _scrub_breadcrumb(breadcrumb: dict[str, Any]) -> dict[str, Any]:
    """Scrub PII from a single breadcrumb."""
    if "message" in breadcrumb and isinstance(breadcrumb["message"], str):
        breadcrumb["message"] = _redactor.mask(breadcrumb["message"])
    if "data" in breadcrumb and isinstance(breadcrumb["data"], dict):
        breadcrumb["data"] = _scrub_dict(breadcrumb["data"])
    return breadcrumb


def _filter_breadcrumb_pii(breadcrumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Sentry before_breadcrumb hook: strip PII from breadcrumbs."""
    return _scrub_breadcrumb(breadcrumb)


def set_sentry_context(
    *,
    trace_id: str | None = None,
    langfuse_trace_id: str | None = None,
    request_id: str | None = None,
    tenant_id: str | None = None,
    bot_instance_id: str | None = None,
    deployment_id: str | None = None,
    service: str | None = None,
    component: str | None = None,
    environment: str | None = None,
    release: str | None = None,
) -> None:
    """Set Sentry context and tags for correlation."""
    context: dict[str, str] = {}
    tags: dict[str, str] = {}

    pairs = [
        ("trace_id", trace_id),
        ("langfuse_trace_id", langfuse_trace_id),
        ("request_id", request_id),
        ("tenant_id", tenant_id),
        ("bot_instance_id", bot_instance_id),
        ("deployment_id", deployment_id),
        ("service", service),
        ("component", component),
        ("environment", environment),
        ("release", release),
    ]

    for key, value in pairs:
        if value is not None:
            context[key] = value
            tags[key] = value

    if context:
        sentry_sdk.set_context("observability", context)
    for tag_key, tag_value in tags.items():
        sentry_sdk.set_tag(tag_key, tag_value)


def set_sentry_user(
    *,
    telegram_user_id_hash: str | None = None,
    chat_id_hash: str | None = None,
) -> None:
    """Set Sentry user context with hashed identifiers."""
    user: dict[str, str] = {}
    if telegram_user_id_hash is not None:
        user["id"] = telegram_user_id_hash
    if chat_id_hash is not None:
        user["chat_id_hash"] = chat_id_hash
    if user:
        sentry_sdk.set_user(user)
