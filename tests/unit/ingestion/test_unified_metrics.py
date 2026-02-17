# tests/unit/ingestion/test_unified_metrics.py
"""Tests for unified ingestion metrics: structured logging and timing."""

import logging
from datetime import UTC, datetime

import pytest

from src.ingestion.unified.metrics import (
    IngestionMetrics,
    log_batch_summary,
    log_ingestion_result,
    timed_operation,
)


class TestIngestionMetrics:
    """Test IngestionMetrics dataclass."""

    def test_defaults(self):
        """New metrics have sensible defaults."""
        m = IngestionMetrics(file_id="abc123", source_path="docs/a.pdf")
        assert m.file_id == "abc123"
        assert m.source_path == "docs/a.pdf"
        assert m.status == "pending"
        assert m.chunks_created == 0
        assert m.chunks_deleted == 0
        assert m.docling_duration_ms == 0
        assert m.voyage_duration_ms == 0
        assert m.qdrant_duration_ms == 0
        assert m.total_duration_ms == 0
        assert m.error_message is None
        assert isinstance(m.started_at, datetime)

    def test_started_at_is_utc(self):
        """started_at uses UTC timezone."""
        m = IngestionMetrics(file_id="x", source_path="x.pdf")
        assert m.started_at.tzinfo == UTC


class TestToStructuredLog:
    """Test IngestionMetrics.to_structured_log()."""

    def test_contains_all_fields(self):
        """Structured log contains all required fields."""
        m = IngestionMetrics(file_id="f1", source_path="docs/f1.pdf")
        m.status = "success"
        m.chunks_created = 10
        m.chunks_deleted = 2
        m.docling_duration_ms = 100.123
        m.voyage_duration_ms = 200.456
        m.qdrant_duration_ms = 50.789
        m.total_duration_ms = 351.368

        log = m.to_structured_log()

        assert log["event"] == "ingestion_file"
        assert log["file_id"] == "f1"
        assert log["source_path"] == "docs/f1.pdf"
        assert log["status"] == "success"
        assert log["chunks_created"] == 10
        assert log["chunks_deleted"] == 2
        assert log["error"] is None

    def test_durations_rounded(self):
        """Duration fields are rounded to 1 decimal."""
        m = IngestionMetrics(file_id="f1", source_path="x.pdf")
        m.docling_duration_ms = 100.1567
        m.voyage_duration_ms = 200.4321
        m.qdrant_duration_ms = 50.789
        m.total_duration_ms = 351.3778

        log = m.to_structured_log()

        assert log["docling_ms"] == 100.2
        assert log["voyage_ms"] == 200.4
        assert log["qdrant_ms"] == 50.8
        assert log["total_ms"] == 351.4

    def test_timestamp_is_iso(self):
        """Timestamp field is ISO 8601 string."""
        m = IngestionMetrics(file_id="f1", source_path="x.pdf")
        log = m.to_structured_log()
        # Should parse without error
        datetime.fromisoformat(log["timestamp"])

    def test_error_message_included(self):
        """Error message appears in log when set."""
        m = IngestionMetrics(file_id="f1", source_path="x.pdf")
        m.error_message = "Connection refused"
        log = m.to_structured_log()
        assert log["error"] == "Connection refused"


class TestTimedOperation:
    """Test timed_operation() context manager."""

    @pytest.mark.parametrize(
        ("operation", "attr", "start", "end"),
        [
            ("docling", "docling_duration_ms", 100.0, 100.011),
            ("voyage", "voyage_duration_ms", 200.0, 200.022),
            ("qdrant", "qdrant_duration_ms", 300.0, 300.033),
        ],
    )
    def test_records_duration_for_operation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        operation: str,
        attr: str,
        start: float,
        end: float,
    ):
        """timed_operation stores elapsed time in the correct attr."""
        values = iter([start, end])
        monkeypatch.setattr(
            "src.ingestion.unified.metrics.time.perf_counter",
            lambda: next(values),
        )
        m = IngestionMetrics(file_id="f1", source_path="x.pdf")
        with timed_operation(m, operation):
            pass
        assert getattr(m, attr) == pytest.approx((end - start) * 1000)

    def test_unknown_operation_is_noop(self):
        """Unknown operation name does not crash."""
        m = IngestionMetrics(file_id="f1", source_path="x.pdf")
        with timed_operation(m, "nonexistent"):
            pass
        # No crash, no attr set

    def test_timing_on_exception(self, monkeypatch: pytest.MonkeyPatch):
        """Duration is still recorded even if the block raises."""
        values = iter([400.0, 400.005])
        monkeypatch.setattr(
            "src.ingestion.unified.metrics.time.perf_counter",
            lambda: next(values),
        )
        m = IngestionMetrics(file_id="f1", source_path="x.pdf")
        with pytest.raises(ValueError, match="boom"):
            with timed_operation(m, "docling"):
                raise ValueError("boom")
        assert m.docling_duration_ms == pytest.approx(5.0)


class TestLogIngestionResult:
    """Test log_ingestion_result() structured logging."""

    def test_success_logs_info(self, caplog):
        """Success status logs at INFO level."""
        m = IngestionMetrics(file_id="f1", source_path="docs/a.pdf")
        m.status = "success"
        m.chunks_created = 5
        with caplog.at_level(logging.INFO, logger="src.ingestion.unified.metrics"):
            log_ingestion_result(m)
        assert "Ingested docs/a.pdf" in caplog.text
        assert "5 chunks" in caplog.text

    def test_skipped_logs_debug(self, caplog):
        """Skipped status logs at DEBUG level."""
        m = IngestionMetrics(file_id="f1", source_path="docs/a.pdf")
        m.status = "skipped"
        with caplog.at_level(logging.DEBUG, logger="src.ingestion.unified.metrics"):
            log_ingestion_result(m)
        assert "Skipped unchanged" in caplog.text

    def test_error_logs_error(self, caplog):
        """Error status logs at ERROR level."""
        m = IngestionMetrics(file_id="f1", source_path="docs/a.pdf")
        m.status = "error"
        m.error_message = "Timeout"
        with caplog.at_level(logging.ERROR, logger="src.ingestion.unified.metrics"):
            log_ingestion_result(m)
        assert "Failed docs/a.pdf" in caplog.text
        assert "Timeout" in caplog.text

    def test_pending_no_log(self, caplog):
        """Pending status does not produce a log message."""
        m = IngestionMetrics(file_id="f1", source_path="docs/a.pdf")
        m.status = "pending"
        with caplog.at_level(logging.DEBUG, logger="src.ingestion.unified.metrics"):
            log_ingestion_result(m)
        assert caplog.text == ""


class TestLogBatchSummary:
    """Test log_batch_summary()."""

    def test_logs_batch_info(self, caplog):
        """Batch summary logs at INFO level with correct counts."""
        with caplog.at_level(logging.INFO, logger="src.ingestion.unified.metrics"):
            log_batch_summary(
                processed=10, skipped=3, failed=1, deleted=2, total_duration_ms=5432.1
            )
        assert "processed=10" in caplog.text
        assert "skipped=3" in caplog.text
        assert "failed=1" in caplog.text
        assert "deleted=2" in caplog.text
        assert "5432" in caplog.text
