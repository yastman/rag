"""Tests for unified ingestion observability helpers."""

from __future__ import annotations

import pytest

from src.ingestion.unified.observability import update_ingestion_trace


pytestmark = pytest.mark.requires_extras


def test_update_ingestion_trace_is_noop() -> None:
    """update_ingestion_trace is a no-op after tracing removal (#2844, #2951, #2969).

    It must not import or reference src.observability (Langfuse shims removed).
    """
    # Verify the function runs without error with typical arguments
    update_ingestion_trace(command="preflight", status="ok", metadata={"step": "boot"})
    update_ingestion_trace(command="run", status="error", metadata={"error": "timeout"})
    update_ingestion_trace(command="bootstrap", status="ok")
    # verify it returns None
    assert update_ingestion_trace(command="check", status="ok") is None


def test_flush_ingestion_traces_is_noop() -> None:
    """flush_ingestion_traces is a no-op after tracing removal."""
    from src.ingestion.unified.observability import flush_ingestion_traces

    assert flush_ingestion_traces() is None


def test_ingestion_session_id_produces_stable_names() -> None:
    """ingestion_session_id builds stable deterministic session names."""
    from src.ingestion.unified.observability import ingestion_session_id

    assert ingestion_session_id("preflight") == "ingestion-preflight"
    assert ingestion_session_id("run") == "ingestion-run"
    assert ingestion_session_id("backfill-colbert") == "ingestion-backfill-colbert"
    assert ingestion_session_id("") == "ingestion-unknown"
    assert ingestion_session_id(None) == "ingestion-unknown"  # type: ignore[arg-type]


def test_try_update_ingestion_trace_wraps_noop() -> None:
    """try_update_ingestion_trace delegates to update_ingestion_trace without error."""
    from src.ingestion.unified.observability import try_update_ingestion_trace

    try_update_ingestion_trace(command="preflight", status="ok")
    try_update_ingestion_trace(command="run", status="error", metadata={"err": "msg"})
