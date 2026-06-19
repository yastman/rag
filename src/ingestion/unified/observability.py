# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""Unified ingestion tracing helpers."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from src.observability import (
    flush_langfuse,
    make_lifecycle_session_id,
    observe,
    update_lifecycle_trace,
)


INGESTION_TAGS = ["ingestion", "unified"]
__all__ = [
    "flush_ingestion_traces",
    "ingestion_session_id",
    "observe",
    "try_update_ingestion_trace",
    "update_ingestion_trace",
]


def flush_ingestion_traces() -> None:
    """Flush buffered ingestion traces on shutdown (best-effort, #2214).

    Wraps :func:`src.observability.flush_langfuse` so CLI entry points can call
    a single ingestion-scoped helper in a ``finally`` block without reaching
    across module boundaries. No-op when tracing was never initialized.
    """
    flush_langfuse()


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
