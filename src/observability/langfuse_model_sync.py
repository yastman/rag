"""Langfuse custom model definition synchronisation.

Extracted from langfuse_client.py. This module handles syncing model price/
tokeniser definitions from ``LANGFUSE_MODEL_DEFINITIONS_JSON`` to Langfuse via
the SDK ``client.api.models`` API.

Public surface: :func:`sync_langfuse_model_definitions`.
Internal helpers are prefixed with ``_`` and not part of the public API.
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger(__name__)

_MODEL_DEFINITIONS_ENV = "LANGFUSE_MODEL_DEFINITIONS_JSON"
_MODEL_SYNC_ENABLED_ENV = "LANGFUSE_MODEL_SYNC_ENABLED"
_MODEL_LIST_PAGE_SIZE = 100


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
    client: Any,
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
        from langfuse.api.commons.types.model_usage_unit import ModelUsageUnit
    except Exception:
        logger.warning("Langfuse model sync skipped: ModelUsageUnit import failed")
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
            create_kwargs = dict(definition)
            unit = create_kwargs.get("unit")
            if isinstance(unit, str) and unit.strip():
                create_kwargs["unit"] = ModelUsageUnit[unit.strip().upper()]
            created = models_api.create(**create_kwargs)
            existing.append(created)
            created_or_updated += 1
        except Exception:
            logger.warning(
                "Langfuse model sync: failed to create model '%s'",
                model_name,
                exc_info=True,
            )

    return created_or_updated
