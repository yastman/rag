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

"""Unified ingestion tracing helpers — tracing removed (#2844, #2951, #2969)."""

from __future__ import annotations

from typing import Any


INGESTION_TAGS = ["ingestion", "unified"]
__all__ = [
    "flush_ingestion_traces",
    "ingestion_session_id",
    "try_update_ingestion_trace",
    "update_ingestion_trace",
]


def flush_ingestion_traces() -> None:
    """No-op — tracing removed (#2844, #2951)."""


def ingestion_session_id(command: str) -> str:
    """Build stable trace session id for ingestion command family."""
    normalized = (command or "").strip().replace(" ", "-")
    return f"ingestion-{normalized or 'unknown'}"


def update_ingestion_trace(
    *,
    command: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """No-op — tracing removed (#2844, #2951, #2969)."""


def try_update_ingestion_trace(
    *,
    command: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Best-effort wrapper for ingestion trace updates (no-op after #2969)."""
    update_ingestion_trace(command=command, status=status, metadata=metadata, trace_id=trace_id)
