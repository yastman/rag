"""PII-safe Langfuse input/output payload builders."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from src.security.pii_redaction import PIIRedactor


_PREVIEW_LIMIT = 240
_redactor = PIIRedactor()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _preview(text: str, *, limit: int = _PREVIEW_LIMIT) -> str:
    """Redact PII first, then bound the preview to ``limit`` chars.

    Redaction happens on the full text so that PII crossing the preview
    boundary is fully matched and replaced before any truncation.
    """
    return cast(str, _redactor.mask(text, max_length=limit))


def build_safe_input_payload(
    content_type: str,
    text: str | None = None,
    action: str | None = None,
    scenario: str | None = None,
    route: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a PII-safe input payload for Langfuse tracing.

    Never includes raw ``text``. Always includes ``content_type``,
    ``query_preview``, ``query_hash``, and ``query_len``.
    """
    payload: dict[str, Any] = {
        "content_type": content_type,
        "query_preview": _preview(text or ""),
        "query_hash": _hash_text(text or ""),
        "query_len": len(text) if text is not None else 0,
    }

    if action is not None:
        payload["action"] = action
    if scenario is not None:
        payload["scenario"] = scenario
    if route is not None:
        payload["route"] = route

    if extra is not None:
        # Keys that must never be overridden or introduced raw.
        # Use a static set that includes all schema keys so that extra can
        # never inject an action/scenario/route when the caller omitted them.
        _SAFE_KEYS = frozenset(
            {
                "content_type",
                "query_preview",
                "query_hash",
                "query_len",
                "action",
                "scenario",
                "route",
            }
        )
        _BLOCKED_EXTRA_KEYS = frozenset({"text", "query", "raw_query", "answer_text", "response"})
        for k, v in extra.items():
            if v is None:
                continue
            if k in _SAFE_KEYS:
                continue  # never override safe payload keys
            if k in _BLOCKED_EXTRA_KEYS:
                continue  # never introduce raw key names
            # Redact and bound extra values (strings, dicts, lists)
            payload[k] = _redactor.mask(v, max_length=_PREVIEW_LIMIT)

    return payload


def build_safe_output_payload(
    answer_text: str | None,
    chunks_count: int,
    delivery_status: str = "sent",
    sources_count: int | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Build a PII-safe output payload for Langfuse tracing.

    Never includes raw ``answer_text`` or ``response``. Always includes
    ``answer_preview``, ``answer_hash``, ``answer_len``, ``chunks_count``,
    and ``delivery_status``.
    """
    safe_text = answer_text or ""
    payload: dict[str, Any] = {
        "answer_preview": _preview(safe_text),
        "answer_hash": _hash_text(safe_text),
        "answer_len": len(safe_text),
        "chunks_count": chunks_count,
        "delivery_status": delivery_status,
    }

    if sources_count is not None:
        payload["sources_count"] = sources_count
    if fallback_reason is not None:
        payload["fallback_reason"] = fallback_reason

    return payload
