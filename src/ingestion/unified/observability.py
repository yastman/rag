"""Unified ingestion tracing helpers."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from telegram_bot.observability import get_client, observe, propagate_attributes


INGESTION_TAGS = ["ingestion", "unified"]
__all__ = [
    "ingestion_session_id",
    "observe",
    "try_update_ingestion_trace",
    "update_ingestion_trace",
]


def ingestion_session_id(command: str) -> str:
    """Build stable trace session id for ingestion command family."""
    normalized = (command or "unknown").strip().replace(" ", "-")
    return f"ingestion-{normalized or 'unknown'}"


def update_ingestion_trace(
    *,
    command: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Update trace metadata for ingestion lifecycle events."""
    session_id = ingestion_session_id(command)
    trace_kwargs: dict[str, Any] = {
        "session_id": session_id,
        "user_id": "ingestion-cli",
        "tags": INGESTION_TAGS,
    }

    payload: dict[str, Any] = {
        "command": command,
        "status": status,
    }
    if metadata:
        payload.update(metadata)

    lf = get_client()
    if lf is None:
        return

    resolved_trace_id = trace_id or lf.create_trace_id(seed=session_id)

    with (
        lf.start_as_current_observation(
            as_type="span",
            name=f"ingestion-{command}",
            trace_context={"trace_id": resolved_trace_id},
        ) as observation,
        propagate_attributes(**trace_kwargs),
    ):
        observation.update(metadata=payload)


def try_update_ingestion_trace(
    *,
    command: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Best-effort wrapper for ingestion trace updates."""
    with suppress(Exception):
        update_ingestion_trace(
            command=command,
            status=status,
            metadata=metadata,
            trace_id=trace_id,
        )
