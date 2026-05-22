"""Unified ingestion tracing helpers."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from src.observability import make_lifecycle_session_id, observe, update_lifecycle_trace


INGESTION_TAGS = ["ingestion", "unified"]
__all__ = [
    "ingestion_session_id",
    "observe",
    "try_update_ingestion_trace",
    "update_ingestion_trace",
]


def ingestion_session_id(command: str) -> str:
    """Build stable trace session id for ingestion command family."""
    return make_lifecycle_session_id("ingestion", command)


def update_ingestion_trace(
    *,
    command: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Update trace metadata for ingestion lifecycle events."""
    payload: dict[str, Any] = {"command": command, "status": status}
    if metadata:
        payload.update(metadata)
    update_lifecycle_trace(
        family="ingestion",
        span_name=f"ingestion-{command}",
        session_id=ingestion_session_id(command),
        user_id="ingestion-cli",
        tags=INGESTION_TAGS,
        metadata=payload,
        trace_id=trace_id,
    )


def try_update_ingestion_trace(
    *,
    command: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Best-effort wrapper for ingestion trace updates."""
    with suppress(Exception):
        update_ingestion_trace(command=command, status=status, metadata=metadata, trace_id=trace_id)
