"""Logs <-> Traces correlation contract (#2217 / Epic G).

Background. The project's JSONFormatter can preserve trace identifiers when
an optional listener or test attaches them to a ``LogRecord``. DEPS-OBS1 removes
monolith OpenTelemetry auto-instrumentation, so this contract only pins the
formatter compatibility surface:

1. ``JSONFormatter`` reads ``record.otelTraceID`` / ``record.otelSpanID``
   when present and emits them as ``trace_id`` / ``span_id`` keys in the
   JSON payload.
2. The keys are absent (not ``null``, not ``"0"``) when there is no active
   trace, so Loki queries can use ``| trace_id != ""`` to filter.
3. The default OTEL "no trace" sentinel ``"0"`` is treated as absence.

"""

from __future__ import annotations

import json
import logging
from typing import Any

from telegram_bot.logging_config import JSONFormatter


def _make_record(**otel_attrs: Any) -> logging.LogRecord:
    """Build a LogRecord, optionally pre-populated with OTEL attrs."""
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="/test.py",
        lineno=42,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    for key, value in otel_attrs.items():
        setattr(record, key, value)
    return record


class TestJsonFormatterEmitsTraceContext:
    def test_emits_trace_id_and_span_id_when_present(self) -> None:
        record = _make_record(
            otelTraceID="abcdef1234567890abcdef1234567890",
            otelSpanID="fedcba0987654321",
        )
        formatted = JSONFormatter().format(record)
        payload = json.loads(formatted)

        assert payload["trace_id"] == "abcdef1234567890abcdef1234567890"
        assert payload["span_id"] == "fedcba0987654321"

    def test_omits_trace_id_when_no_active_trace(self) -> None:
        """No ``record.otelTraceID`` -> no ``trace_id`` key (not null)."""
        record = _make_record()
        formatted = JSONFormatter().format(record)
        payload = json.loads(formatted)

        assert "trace_id" not in payload
        assert "span_id" not in payload

    def test_omits_trace_id_when_otel_sentinel_zero(self) -> None:
        """LoggingInstrumentor injects ``"0"`` when there is no active OTEL
        context — must be treated as absence, not a real trace ID."""
        record = _make_record(otelTraceID="0", otelSpanID="0")
        formatted = JSONFormatter().format(record)
        payload = json.loads(formatted)

        assert "trace_id" not in payload
        assert "span_id" not in payload

    def test_emits_only_trace_id_when_span_missing(self) -> None:
        """Robust to partial population (defensive)."""
        record = _make_record(otelTraceID="trace-xyz")
        formatted = JSONFormatter().format(record)
        payload = json.loads(formatted)

        assert payload["trace_id"] == "trace-xyz"
        assert "span_id" not in payload

    def test_existing_extra_fields_still_emit(self) -> None:
        """Adding trace_id MUST NOT regress the existing extra-fields path."""
        record = _make_record(
            otelTraceID="trace-1",
            otelSpanID="span-1",
            user_id=12345,
            latency_ms=42,
            cache_hit=True,
        )
        formatted = JSONFormatter().format(record)
        payload = json.loads(formatted)

        assert payload["trace_id"] == "trace-1"
        assert payload["user_id"] == 12345
        assert payload["latency_ms"] == 42
        assert payload["cache_hit"] is True
