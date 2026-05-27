"""Tests for Langfuse latency audit probe (#2179).

The probe aggregates per-stage observation latencies from recent traces
into a sanitized p50/p95 report. The aggregator is pure (no I/O) so it
is unit-testable against synthetic observation lists.

Stages of interest (from the issue body): retrieve, cache, checkpoint,
LLM. The probe groups observations into these buckets via name prefix
matching and reports per-bucket latency stats plus a list of missing
stages so the operator can spot incomplete pipelines.
"""

from __future__ import annotations

import pytest

from scripts.probe.langfuse_latency_audit import (
    DEFAULT_LATENCY_BUCKETS,
    LatencyReport,
    aggregate_latencies,
    classify_observation_name,
)


# ---------------------------------------------------------------------------
# Bucket classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected_bucket",
    [
        # Retrieval stages
        ("retrieve", "retrieve"),
        ("retrieve-dense", "retrieve"),
        ("hybrid-search", "retrieve"),
        ("rerank", "retrieve"),
        ("colbert-rerank", "retrieve"),
        # Cache stages
        ("cache-lookup", "cache"),
        ("semantic-cache", "cache"),
        ("redis-cache-get", "cache"),
        # Checkpoint stages
        ("checkpoint-save", "checkpoint"),
        ("langgraph-checkpointer", "checkpoint"),
        # LLM stages
        ("llm-generate", "llm"),
        ("litellm-acompletion", "llm"),
        ("openai-chat", "llm"),
        # Out-of-bucket
        ("graph-router", "other"),
        ("unrelated-thing", "other"),
    ],
)
def test_classify_observation_name(name: str, expected_bucket: str) -> None:
    assert classify_observation_name(name) == expected_bucket


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregate_returns_p50_and_p95_per_bucket() -> None:
    observations = [
        {"name": "retrieve", "latency_ms": 100},
        {"name": "retrieve", "latency_ms": 200},
        {"name": "retrieve", "latency_ms": 300},
        {"name": "retrieve", "latency_ms": 400},
        {"name": "retrieve", "latency_ms": 500},
        {"name": "litellm-acompletion", "latency_ms": 1000},
        {"name": "litellm-acompletion", "latency_ms": 2000},
    ]
    report = aggregate_latencies(observations)
    assert isinstance(report, LatencyReport)
    retrieve = report.buckets["retrieve"]
    assert retrieve.count == 5
    assert retrieve.p50 == 300
    # p95 of 5 samples — definition: nearest-rank, so position 5 → 500
    assert retrieve.p95 == 500

    llm = report.buckets["llm"]
    assert llm.count == 2
    assert llm.p50 in (1000, 2000)


def test_aggregate_handles_missing_buckets() -> None:
    """Buckets with zero observations show count=0 and are flagged missing."""
    observations = [{"name": "retrieve", "latency_ms": 50}]
    report = aggregate_latencies(observations)
    for bucket in DEFAULT_LATENCY_BUCKETS:
        if bucket == "retrieve":
            continue
        assert report.buckets[bucket].count == 0
    assert "cache" in report.missing_stages
    assert "checkpoint" in report.missing_stages
    assert "llm" in report.missing_stages
    assert "retrieve" not in report.missing_stages


def test_aggregate_skips_observations_missing_latency() -> None:
    observations = [
        {"name": "retrieve", "latency_ms": 100},
        {"name": "retrieve"},  # no latency_ms
        {"name": "retrieve", "latency_ms": None},
    ]
    report = aggregate_latencies(observations)
    assert report.buckets["retrieve"].count == 1


def test_aggregate_empty_input_returns_empty_report() -> None:
    report = aggregate_latencies([])
    assert all(b.count == 0 for b in report.buckets.values())
    # Every default bucket is missing.
    assert set(report.missing_stages) == set(DEFAULT_LATENCY_BUCKETS)


def test_report_has_render_method() -> None:
    """Report must produce a stable text render for evidence collection."""
    observations = [{"name": "retrieve", "latency_ms": 100}]
    report = aggregate_latencies(observations)
    rendered = report.render()
    assert "retrieve" in rendered
    assert "p50" in rendered.lower() or "p95" in rendered.lower()
