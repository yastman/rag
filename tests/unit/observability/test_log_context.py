"""Tests for observability log context propagation."""

from __future__ import annotations

import logging

from src.observability.log_context import (
    ObservabilityLogFilter,
    clear_log_context,
    get_log_context,
    set_log_context,
)


class TestSetAndGetLogContext:
    def test_set_and_get_log_context(self) -> None:
        clear_log_context()
        set_log_context(trace_id="t-1", service="bot")
        ctx = get_log_context()
        assert ctx["trace_id"] == "t-1"
        assert ctx["service"] == "bot"
        clear_log_context()

    def test_set_log_context_ignores_none(self) -> None:
        clear_log_context()
        set_log_context(trace_id="t-2", component=None)
        ctx = get_log_context()
        assert "trace_id" in ctx
        assert "component" not in ctx
        clear_log_context()


class TestClearLogContext:
    def test_clear_log_context(self) -> None:
        set_log_context(trace_id="t-3")
        clear_log_context()
        ctx = get_log_context()
        assert ctx == {}


class TestObservabilityLogFilter:
    def test_observability_log_filter_injects_context(self) -> None:
        clear_log_context()
        set_log_context(trace_id="t-4", request_id="r-1")

        log_filter = ObservabilityLogFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=None,
            exc_info=None,
        )

        result = log_filter.filter(record)
        assert result is True
        assert record.trace_id == "t-4"
        assert record.request_id == "r-1"
        clear_log_context()

    def test_observability_log_filter_returns_true_with_empty_context(self) -> None:
        clear_log_context()
        log_filter = ObservabilityLogFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=None,
            exc_info=None,
        )
        assert log_filter.filter(record) is True
