"""Langfuse client initialization logic.

Extracted from langfuse_client.py. This module handles the one-time
initialization of the Langfuse SDK client, OTEL resource attribute wiring,
and environment-based configuration resolution.

Public surface: :func:`initialize_langfuse`.
Internal helpers are prefixed with ``_`` and not part of the public API.
"""

import atexit
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from src.observability.bootstrap import (
    disable_otel_exporter as _disable_otel_exporter,
)
from src.observability.bootstrap import (
    is_endpoint_reachable as _is_endpoint_reachable,
)
from src.observability.langfuse_model_sync import sync_langfuse_model_definitions


logger = logging.getLogger(__name__)

_OTEL_EXPORT_DEFAULTS = {
    "OTEL_BSP_SCHEDULE_DELAY": "30000",
    "OTEL_BSP_EXPORT_TIMEOUT": "10000",
    "OTEL_EXPORTER_OTLP_TIMEOUT": "10000",
}

# Module state — shared with langfuse_client via the accessor functions below.
_langfuse_client: Any = None  # Langfuse | None
_langfuse_init_attempted = False
_langfuse_endpoint_warned = False
# #2214: guard the lazy singleton init.
_langfuse_init_lock = threading.RLock()


def get_langfuse_init_client() -> Any:
    """Return the current initialized client (or None)."""
    return _langfuse_client


def _langfuse_enabled() -> bool:
    """Return whether Langfuse client construction is explicitly enabled."""
    return os.getenv("LANGFUSE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_config_value(explicit: str | None, env_name: str) -> str | None:
    """Resolve explicit override first, then environment variable."""
    value = explicit if explicit is not None else os.getenv(env_name)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _ensure_otel_service_name(default: str) -> None:
    """Set OTEL_SERVICE_NAME to default when absent, preserving explicit config."""
    if not os.environ.get("OTEL_SERVICE_NAME"):
        os.environ["OTEL_SERVICE_NAME"] = default


def _resolve_release(explicit: str | None = None) -> str:
    """Resolve the release/version string for Langfuse + OTEL resource (#2227)."""
    candidate = explicit if explicit is not None else os.getenv("LANGFUSE_RELEASE", "")
    candidate = (candidate or "").strip()
    if candidate:
        return candidate
    try:
        from importlib import metadata as _metadata

        return f"contextual-rag@{_metadata.version('contextual-rag')}"
    except Exception:
        return "contextual-rag@unknown"


def _ensure_otel_resource_attributes(*, service_namespace: str = "rag") -> None:
    """Merge OTEL resource attributes into ``OTEL_RESOURCE_ATTRIBUTES`` (#2227)."""
    existing_raw = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    merged: dict[str, str] = {}
    for pair in existing_raw.split(","):
        pair = pair.strip()
        if pair and "=" in pair:
            key, val = pair.split("=", 1)
            key, val = key.strip(), val.strip()
            if val:
                merged[key] = val

    defaults: dict[str, str] = {
        "service.version": _resolve_release(),
        "service.namespace": service_namespace,
    }
    tracing_env = (os.environ.get("LANGFUSE_TRACING_ENVIRONMENT", "") or "").strip()
    if tracing_env:
        defaults["deployment.environment"] = tracing_env
    try:
        import socket

        defaults["host.name"] = socket.gethostname()
    except Exception:
        defaults["host.name"] = "unknown"

    for key, val in defaults.items():
        merged.setdefault(key, val)

    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(f"{k}={v}" for k, v in sorted(merged.items()))


def _ensure_otel_export_defaults() -> None:
    """Set conservative OTEL export defaults unless explicitly configured."""
    for env_name, default in _OTEL_EXPORT_DEFAULTS.items():
        if not os.environ.get(env_name):
            os.environ[env_name] = default


def initialize_langfuse(
    *,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    force: bool = False,
    _langfuse_cls: Any = None,
    _mask_fn: Callable[..., Any] | None = None,
) -> Any:  # returns Langfuse | None
    """Initialize a Langfuse client after runtime config is loaded.

    Returns None when credentials are missing, endpoint unreachable, or client creation fails.
    Thread-safe (#2214).
    """
    if _langfuse_client is not None and not force:
        return _langfuse_client
    with _langfuse_init_lock:
        return _initialize_langfuse_locked(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            force=force,
            _langfuse_cls=_langfuse_cls,
            _mask_fn=_mask_fn,
        )


def _initialize_langfuse_locked(
    *,
    public_key: str | None,
    secret_key: str | None,
    host: str | None,
    force: bool,
    _langfuse_cls: Any = None,
    _mask_fn: Callable[..., Any] | None = None,
) -> Any:  # returns Langfuse | None
    """Body of :func:`initialize_langfuse`; must run while holding the lock."""
    global _langfuse_client
    global _langfuse_init_attempted
    global _langfuse_endpoint_warned

    if _langfuse_client is not None and not force:
        return _langfuse_client

    # Resolve the Langfuse class and availability.
    langfuse_available: bool
    langfuse_import_error: Exception | None
    if _langfuse_cls is not None:
        langfuse_available = True
        langfuse_import_error = None
    else:
        try:
            from langfuse import Langfuse as _Langfuse

            _langfuse_cls = _Langfuse
            langfuse_available = True
            langfuse_import_error = None
        except Exception as _e:
            langfuse_available = False
            langfuse_import_error = _e

    explicit_config = public_key is not None or secret_key is not None or host is not None
    if not explicit_config and not _langfuse_enabled():
        _langfuse_client = None
        if force or not _langfuse_init_attempted:
            logger.info("Langfuse disabled (set LANGFUSE_ENABLED=true to enable optional listener)")
        _langfuse_init_attempted = True
        _disable_otel_exporter()
        return None

    if _langfuse_init_attempted and _langfuse_client is None and not force:
        return None

    if not langfuse_available:
        _langfuse_client = None
        if not _langfuse_init_attempted:
            logger.warning("Langfuse SDK unavailable (import failed): %s", langfuse_import_error)
        _langfuse_init_attempted = True
        _disable_otel_exporter()
        return None

    resolved_public_key = _resolve_config_value(public_key, "LANGFUSE_PUBLIC_KEY")
    resolved_secret_key = _resolve_config_value(secret_key, "LANGFUSE_SECRET_KEY")
    resolved_host = _resolve_config_value(host, "LANGFUSE_HOST")

    if not resolved_public_key or not resolved_secret_key:
        _langfuse_client = None
        if force or not _langfuse_init_attempted:
            logger.info("Langfuse disabled (missing LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)")
        _langfuse_init_attempted = True
        _disable_otel_exporter()
        return None

    if resolved_host and not _is_endpoint_reachable(resolved_host):
        _langfuse_client = None
        _langfuse_init_attempted = True
        if not _langfuse_endpoint_warned:
            _langfuse_endpoint_warned = True
            logger.warning(
                "Langfuse endpoint unreachable (%s) — tracing disabled. "
                "Start Langfuse locally or unset LANGFUSE_HOST to suppress this warning.",
                resolved_host,
            )
        _disable_otel_exporter(shutdown=False)
        return None

    kwargs: dict[str, Any] = {
        "public_key": resolved_public_key,
        "secret_key": resolved_secret_key,
    }
    if _mask_fn is not None:
        kwargs["mask"] = _mask_fn  # type: ignore[arg-type]
    if resolved_host:
        kwargs["host"] = resolved_host
    tracing_env = os.environ.get("LANGFUSE_TRACING_ENVIRONMENT")
    if tracing_env:
        kwargs["environment"] = tracing_env
    kwargs["release"] = _resolve_release()

    _ensure_otel_service_name("telegram-bot")
    _ensure_otel_resource_attributes()
    _ensure_otel_export_defaults()
    try:
        kwargs["flush_at"] = int(os.environ.get("LANGFUSE_FLUSH_AT", "512"))
        kwargs["flush_interval"] = float(os.environ.get("LANGFUSE_FLUSH_INTERVAL", "5.0"))
        _langfuse_client = _langfuse_cls(**kwargs)
        atexit.register(_langfuse_client.shutdown)
        _langfuse_init_attempted = True
        synced = sync_langfuse_model_definitions(_langfuse_client)
        if synced > 0:
            logger.info("Langfuse model definitions synced: %d", synced)
        logger.info("Langfuse observability initialized")
        return _langfuse_client
    except Exception:
        logger.warning("Failed to initialize Langfuse client", exc_info=True)
        _langfuse_client = None
        _langfuse_init_attempted = True
        _disable_otel_exporter(shutdown=False)
        return None


def _reset_langfuse_init_state() -> None:
    """Reset module-level init state (test-only helper)."""
    global _langfuse_client
    global _langfuse_init_attempted
    global _langfuse_endpoint_warned
    _langfuse_client = None
    _langfuse_init_attempted = False
    _langfuse_endpoint_warned = False
