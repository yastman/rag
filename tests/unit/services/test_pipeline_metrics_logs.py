"""Pipeline metric helpers emit structured product logs, not Prometheus state."""

from __future__ import annotations

import logging

from src.runtime.services.metrics import (
    PipelineMetrics,
    record_counter_metric,
    record_pipeline_event,
    record_pipeline_latency,
)


def _product_records(caplog):
    return [r for r in caplog.records if r.name == "src.utils.product_events"]


def test_record_pipeline_latency_logs_metric_fields(caplog) -> None:
    caplog.set_level(logging.INFO, logger="src.utils.product_events")

    record_pipeline_latency("retrieve", 0.123, request_id="req-1")

    [record] = _product_records(caplog)
    assert record.event == "pipeline_latency"
    assert record.request_id == "req-1"
    assert record.stage == "retrieve"
    assert record.metric_name == "pipeline.retrieve.latency_ms"
    assert record.metric_value == 123.0
    assert record.latency_ms == 123.0


def test_record_pipeline_event_logs_counter_fields(caplog) -> None:
    caplog.set_level(logging.INFO, logger="src.utils.product_events")

    record_pipeline_event("cache_hit", 2, request_id="req-2")

    [record] = _product_records(caplog)
    assert record.event == "pipeline_counter"
    assert record.request_id == "req-2"
    assert record.metric_name == "cache_hit"
    assert record.metric_value == 2
    assert record.count == 2


def test_counter_helpers_ignore_non_positive_values(caplog) -> None:
    caplog.set_level(logging.INFO, logger="src.utils.product_events")

    record_pipeline_event("cache_hit", 0)
    record_counter_metric("cache_miss", -1)

    assert _product_records(caplog) == []


def test_pipeline_metrics_facade_preserves_record_and_inc(caplog) -> None:
    caplog.set_level(logging.INFO, logger="src.utils.product_events")
    PipelineMetrics.reset()
    metrics = PipelineMetrics.get()

    metrics.record("generate", 42.5, request_id="req-3")
    metrics.inc("retrieval_zero_docs", request_id="req-3")

    records = _product_records(caplog)
    assert [r.event for r in records] == ["pipeline_latency", "pipeline_counter"]
    assert records[0].metric_name == "pipeline.generate.latency_ms"
    assert records[0].latency_ms == 42.5
    assert records[1].metric_name == "retrieval_zero_docs"
    assert records[1].count == 1
