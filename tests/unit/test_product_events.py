"""Unit tests for src.utils.product_events — log_event helper and JSON formatter.

Tests cover: basic JSON output, falsy field preservation, optional field handling,
and absence of Langfuse/OTel/FastAPI/Telegram/aiogram imports.
"""

from __future__ import annotations

import json
import logging


# ---------------------------------------------------------------------------
# JSON formatter tests
# ---------------------------------------------------------------------------


def test_json_formatter_preserves_event_top_level() -> None:
    """Event must be a top-level key in the JSON output."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="retrieved_documents",
        args=None,
        exc_info=None,
    )
    record.event = "retrieved_documents"
    record.request_id = "req-123"
    record.retrieved_doc_ids = ["doc-1", "doc-2"]

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert data["event"] == "retrieved_documents"
    assert data["module"] == "test"


def test_json_formatter_falsy_zero_preserved() -> None:
    """Falsy int 0 must appear in output (not be dropped)."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="llm_usage",
        args=None,
        exc_info=None,
    )
    record.event = "llm_usage"
    record.input_tokens = 0
    record.output_tokens = 0

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert data["input_tokens"] == 0
    assert data["output_tokens"] == 0


def test_json_formatter_falsy_false_preserved() -> None:
    """Falsy False must appear in output (not be dropped)."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="cache_hit",
        args=None,
        exc_info=None,
    )
    record.event = "cache_hit"
    record.hit = False

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert data["hit"] is False


def test_json_formatter_falsy_none_preserved() -> None:
    """Falsy None must appear in output (not be dropped)."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="llm_call",
        args=None,
        exc_info=None,
    )
    record.event = "llm_call"
    record.error_type = None

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert data["error_type"] is None


def test_json_formatter_all_common_fields() -> None:
    """All supported optional fields should be present in JSON output."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="query_executed",
        args=None,
        exc_info=None,
    )
    record.event = "query_executed"
    record.request_id = "abc-456"
    record.route = "POST /query"
    record.latency_ms = 42.5
    record.error_type = None
    record.retrieved_doc_ids = ["d1", "d2"]
    record.llm_model = "gpt-4o-mini"
    record.input_tokens = 120
    record.output_tokens = 350

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert data["event"] == "query_executed"
    assert data["request_id"] == "abc-456"
    assert data["route"] == "POST /query"
    assert data["latency_ms"] == 42.5
    assert data["error_type"] is None
    assert data["retrieved_doc_ids"] == ["d1", "d2"]
    assert data["llm_model"] == "gpt-4o-mini"
    assert data["input_tokens"] == 120
    assert data["output_tokens"] == 350


def test_json_formatter_absent_fields_not_in_output() -> None:
    """Keys that are not set on the record must not appear in JSON."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="cache_hit",
        args=None,
        exc_info=None,
    )
    record.event = "cache_hit"

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert "latency_ms" not in data
    assert "retrieved_doc_ids" not in data
    assert "llm_model" not in data


def test_json_formatter_does_not_serialize_logrecord_methods() -> None:
    """Formatter must not leak LogRecord methods as product metadata."""
    from src.utils.product_events import ProductEventsFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="/app/src/test.py",
        lineno=0,
        msg="query_executed",
        args=None,
        exc_info=None,
    )
    record.event = "query_executed"
    record.request_id = "req-methods"

    fmt = ProductEventsFormatter()
    output = fmt.format(record)
    data = json.loads(output)

    assert "getMessage" not in data
    assert "get_message" not in data


# ---------------------------------------------------------------------------
# log_event helper tests
# ---------------------------------------------------------------------------


def _format_with_product_formatter(records: list[logging.LogRecord]) -> str:
    """Format caplog records via ProductEventsFormatter so we can decode JSON."""
    from src.utils.product_events import ProductEventsFormatter

    fmt = ProductEventsFormatter()
    return fmt.format(records[0])


def test_log_event_emits_json_to_stream(caplog: pytest.LogCaptureFixture) -> None:
    """log_event should emit a JSON line via standard logging at INFO level."""
    from src.utils.product_events import log_event

    with caplog.at_level(logging.INFO):
        log_event("query_executed", request_id="r-1", latency_ms=12.5)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "INFO"

    data = json.loads(_format_with_product_formatter(caplog.records))
    assert data["event"] == "query_executed"
    assert data["request_id"] == "r-1"
    assert data["latency_ms"] == 12.5


def test_log_event_falsy_values_preserved(caplog: pytest.LogCaptureFixture) -> None:
    """Falsy values passed to log_event must survive serialization."""
    from src.utils.product_events import log_event

    with caplog.at_level(logging.INFO):
        log_event("llm_usage", input_tokens=0, output_tokens=0, hit=False, error_type=None)

    assert len(caplog.records) == 1

    data = json.loads(_format_with_product_formatter(caplog.records))
    assert data["input_tokens"] == 0
    assert data["output_tokens"] == 0
    # hit=False is an unknown field, silently dropped by log_event gate
    assert data["error_type"] is None


def test_log_event_uses_event_as_message() -> None:
    """The formatted JSON output must include event name as a top-level key."""
    import io

    from src.utils.product_events import ProductEventsFormatter

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(ProductEventsFormatter())
    logger = logging.getLogger("src.utils.product_events.test_log_event")
    logger.propagate = False
    # Clear any pre-existing handlers from import-time setup
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    extra = {"event": "cache_hit", "hit": True}
    logger.info("cache_hit", extra=extra)
    handler.flush()
    output = buf.getvalue().strip()

    data = json.loads(output)
    assert data["event"] == "cache_hit"
    assert data["message"] == "cache_hit"


def test_log_event_unknown_field_silently_dropped(caplog: pytest.LogCaptureFixture) -> None:
    """Fields not in _PRODUCT_FIELDS must be silently ignored (no crash, no leak)."""
    from src.utils.product_events import log_event

    with caplog.at_level(logging.INFO):
        log_event("some_event", request_id="abc", secret_field="SEKRET")

    assert len(caplog.records) == 1

    data = json.loads(_format_with_product_formatter(caplog.records))
    assert data["event"] == "some_event"
    assert data["request_id"] == "abc"
    assert "secret_field" not in data


# ---------------------------------------------------------------------------
# Import isolation contract
# ---------------------------------------------------------------------------


def test_module_imports_no_langfuse_or_otel() -> None:
    """The product_events module must not import Langfuse or OTel directly."""
    import importlib

    import src.utils.product_events  # noqa: F401 — trigger first import

    mod_src = importlib.import_module("src.utils.product_events")
    for forbidden in ("langfuse", "opentelemetry", "otel", "fastapi", "telegram", "aiogram"):
        assert forbidden not in mod_src.__dict__, (
            f"src.utils.product_events must not import {forbidden}"
        )


# ---------------------------------------------------------------------------
# pytest marker registration
# ---------------------------------------------------------------------------

import pytest
