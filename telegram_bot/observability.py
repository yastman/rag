"""Langfuse observability helpers with runtime initialization.

This module always exposes the real Langfuse SDK APIs (`observe`, `get_client`,
`propagate_attributes`) and relies on SDK-native graceful degradation when
credentials are unavailable.

Use `initialize_langfuse()` after loading runtime config (e.g. BotConfig) to
ensure credentials from `.env`/environment are applied before first tracing.
"""

import atexit
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from langfuse import (
    Langfuse,
)
from langfuse import (
    get_client as _real_get_client,
)
from langfuse import (
    observe as _real_observe,
)
from langfuse import (
    propagate_attributes as _real_propagate,
)

from src.security.pii_redaction import PIIRedactor
from telegram_bot.observability_bootstrap import (
    disable_otel_exporter as _bootstrap_disable_otel_exporter,
)
from telegram_bot.observability_bootstrap import (
    is_endpoint_reachable as _bootstrap_is_endpoint_reachable,
)


logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None
_langfuse_init_attempted = False

_MAX_PII_TEXT_LENGTH = 4000
_MODEL_DEFINITIONS_ENV = "LANGFUSE_MODEL_DEFINITIONS_JSON"
_MODEL_SYNC_ENABLED_ENV = "LANGFUSE_MODEL_SYNC_ENABLED"
_MODEL_LIST_PAGE_SIZE = 100

_pii_redactor = PIIRedactor()

_langfuse_endpoint_warned = False


def _is_endpoint_reachable(url: str, *, timeout: float = 2.0) -> bool:
    """Compatibility wrapper used by unit tests and init flow."""
    return _bootstrap_is_endpoint_reachable(url, timeout=timeout)


def _disable_otel_exporter() -> None:
    """Compatibility wrapper used by unit tests and init flow."""
    _bootstrap_disable_otel_exporter()


# ---------------------------------------------------------------------------
# PII masking (always available)
# ---------------------------------------------------------------------------


def mask_pii(data: Any) -> Any:
    """Mask PII before sending to Langfuse.

    Applied to all inputs/outputs/metadata automatically.
    Delegates to PIIRedactor for pattern matching; truncates long strings.

    Masks:
    - Ukrainian passport numbers
    - Tax IDs (РНОКПП, 10 digits)
    - Telegram user IDs (9-10 digits)
    - Phone numbers (10-15 digits with optional +)
    - Email addresses
    - Long texts (>4000 chars truncated)
    """
    return _pii_redactor.mask(data, max_length=_MAX_PII_TEXT_LENGTH)


# ---------------------------------------------------------------------------
# Public SDK exports
# ---------------------------------------------------------------------------

observe = _real_observe
get_client = _real_get_client
propagate_attributes = _real_propagate


def _resolve_config_value(explicit: str | None, env_name: str) -> str | None:
    """Resolve explicit override first, then environment variable."""
    value = explicit if explicit is not None else os.getenv(env_name)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _normalize_unit(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip().upper()
    else:
        candidate = str(getattr(value, "value", value)).strip().upper()
    return candidate or None


def _normalize_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _load_model_definitions_from_env() -> list[dict[str, Any]]:
    """Load custom Langfuse model definitions from JSON env."""
    raw = os.getenv(_MODEL_DEFINITIONS_ENV, "").strip()
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid %s JSON, skipping model definition sync", _MODEL_DEFINITIONS_ENV)
        return []

    entries: list[Any]
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = [payload]
    else:
        logger.warning("%s must be list/dict, got %s", _MODEL_DEFINITIONS_ENV, type(payload))
        return []

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            logger.warning(
                "Skipping model definition #%d: expected object, got %s", idx, type(item)
            )
            continue

        model_name = str(item.get("model_name", "")).strip()
        match_pattern = str(item.get("match_pattern", "")).strip()
        if not model_name or not match_pattern:
            logger.warning(
                "Skipping model definition #%d: model_name and match_pattern are required",
                idx,
            )
            continue

        definition: dict[str, Any] = {
            "model_name": model_name,
            "match_pattern": match_pattern,
        }

        unit = _normalize_unit(item.get("unit"))
        if unit:
            definition["unit"] = unit

        start_date = _normalize_datetime(item.get("start_date"))
        if start_date is not None:
            definition["start_date"] = start_date

        for key in ("input_price", "output_price", "total_price"):
            value = _to_float(item.get(key))
            if value is not None:
                definition[key] = value

        tokenizer_id = item.get("tokenizer_id")
        if isinstance(tokenizer_id, str) and tokenizer_id.strip():
            definition["tokenizer_id"] = tokenizer_id.strip()

        tokenizer_config = item.get("tokenizer_config")
        if isinstance(tokenizer_config, dict) and tokenizer_config:
            definition["tokenizer_config"] = tokenizer_config

        normalized.append(definition)

    return normalized


def _model_definitions_equal(existing: Any, target: dict[str, Any]) -> bool:
    if str(getattr(existing, "model_name", "")).strip() != target["model_name"]:
        return False
    if str(getattr(existing, "match_pattern", "")).strip() != target["match_pattern"]:
        return False

    existing_unit = _normalize_unit(getattr(existing, "unit", None))
    target_unit = _normalize_unit(target.get("unit"))
    if existing_unit != target_unit:
        return False

    for key in ("input_price", "output_price", "total_price"):
        existing_price = _to_float(getattr(existing, key, None))
        target_price = _to_float(target.get(key))
        if existing_price != target_price:
            return False

    existing_tokenizer = getattr(existing, "tokenizer_id", None)
    target_tokenizer = target.get("tokenizer_id")
    return (existing_tokenizer or None) == (target_tokenizer or None)


def sync_langfuse_model_definitions(
    client: Langfuse | None,
    *,
    definitions: list[dict[str, Any]] | None = None,
) -> int:
    """Ensure Langfuse custom model definitions are present via SDK API."""
    if client is None:
        return 0

    if os.getenv(_MODEL_SYNC_ENABLED_ENV, "true").strip().lower() in {"0", "false", "no"}:
        return 0

    model_definitions = (
        definitions if definitions is not None else _load_model_definitions_from_env()
    )
    if not model_definitions:
        return 0

    api = getattr(client, "api", None)
    models_api = getattr(api, "models", None) if api is not None else None
    if models_api is None:
        logger.warning("Langfuse model sync skipped: client.api.models unavailable")
        return 0

    try:
        from langfuse.api.resources.models.types.create_model_request import CreateModelRequest
    except Exception:
        logger.warning("Langfuse model sync skipped: CreateModelRequest import failed")
        return 0

    existing: list[Any] = []
    page = 1
    while True:
        try:
            page_data = models_api.list(page=page, limit=_MODEL_LIST_PAGE_SIZE)
        except Exception:
            logger.warning("Langfuse model sync skipped: unable to list models", exc_info=True)
            return 0
        rows = list(getattr(page_data, "data", []) or [])
        existing.extend(rows)
        if len(rows) < _MODEL_LIST_PAGE_SIZE:
            break
        page += 1

    created_or_updated = 0
    for definition in model_definitions:
        model_name = definition["model_name"]
        same_name = [m for m in existing if getattr(m, "model_name", None) == model_name]
        custom = [m for m in same_name if not bool(getattr(m, "is_langfuse_managed", False))]

        current = custom[0] if custom else None
        if current and _model_definitions_equal(current, definition):
            continue

        if current is not None:
            model_id = getattr(current, "id", None)
            if isinstance(model_id, str) and model_id:
                try:
                    models_api.delete(model_id)
                except Exception:
                    logger.warning(
                        "Langfuse model sync: failed to delete stale model '%s' (%s)",
                        model_name,
                        model_id,
                        exc_info=True,
                    )
                    continue
                existing = [m for m in existing if getattr(m, "id", None) != model_id]

        try:
            created = models_api.create(request=CreateModelRequest(**definition))
            existing.append(created)
            created_or_updated += 1
        except Exception:
            logger.warning(
                "Langfuse model sync: failed to create model '%s'",
                model_name,
                exc_info=True,
            )

    return created_or_updated


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
    """
    global _langfuse_client
    global _langfuse_init_attempted
    global _langfuse_endpoint_warned

    if _langfuse_client is not None and not force:
        return _langfuse_client

    # Return cached None without re-logging when already attempted
    if _langfuse_init_attempted and _langfuse_client is None and not force:
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

    # Probe endpoint reachability only when an explicit host is configured.
    # Cloud default (no host) is assumed reachable to avoid blocking startup.
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
        _disable_otel_exporter()
        return None

    kwargs: dict[str, Any] = {
        "public_key": resolved_public_key,
        "secret_key": resolved_secret_key,
        "mask": mask_pii,  # type: ignore[arg-type]  # MaskFunction typing mismatch
    }
    if resolved_host:
        kwargs["host"] = resolved_host
    tracing_env = os.environ.get("LANGFUSE_TRACING_ENVIRONMENT")
    if tracing_env:
        kwargs["environment"] = tracing_env

    try:
        kwargs["flush_at"] = int(os.environ.get("LANGFUSE_FLUSH_AT", "512"))
        kwargs["flush_interval"] = float(os.environ.get("LANGFUSE_FLUSH_INTERVAL", "5.0"))
        _langfuse_client = Langfuse(**kwargs)
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
        _disable_otel_exporter()
        return None


def get_langfuse_client() -> Langfuse | None:
    """Get initialized Langfuse client, lazy-initializing from env when possible."""
    if _langfuse_client is not None:
        return _langfuse_client
    return initialize_langfuse()


def create_callback_handler(
    *,
    trace_context: Any | None = None,
    update_trace: bool = False,
):
    """Create Langfuse CallbackHandler for create_agent integration.

    Returns None when Langfuse is not configured or handler init fails.
    """
    if get_langfuse_client() is None:
        return None

    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(
            trace_context=trace_context,
            update_trace=update_trace,
        )
    except Exception:
        logger.warning("Failed to create Langfuse CallbackHandler", exc_info=True)
        return None


def traced_pipeline(
    *,
    session_id: str,
    user_id: str,
    tags: list[str] | None = None,
):
    """Context manager for pipeline-level trace propagation.

    Wraps propagate_attributes with sensible defaults.
    Use at any entry point that invokes @observe-decorated functions.
    """
    return propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=tags or [],
    )


def _reset_langfuse_client_for_tests() -> None:
    """Reset module-level client cache (test-only helper)."""
    global _langfuse_client
    global _langfuse_init_attempted
    global _langfuse_endpoint_warned
    _langfuse_client = None
    _langfuse_init_attempted = False
    _langfuse_endpoint_warned = False
