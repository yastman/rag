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

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.probe.langfuse_latency_audit import (
    DEFAULT_LATENCY_BUCKETS,
    LatencyReport,
    _collect_from_langfuse,
    aggregate_latencies,
    classify_observation_name,
)


SCRIPT = Path("scripts/probe/langfuse_latency_audit.py")


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT.resolve()), *args],
        capture_output=True,
        text=True,
        cwd=SCRIPT.parents[2],
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


def test_live_collection_uses_langfuse_observations_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Langfuse v4 exposes observation pages via api.observations.get_many()."""
    calls: dict[str, object] = {}

    class FakeObservations:
        def get_many(self, **kwargs: object) -> object:
            calls.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(name="retrieve", latency=0.125),
                    SimpleNamespace(name="litellm-acompletion", latency=1.5),
                    SimpleNamespace(name=None, latency=99),
                    SimpleNamespace(name="cache", latency=None),
                ]
            )

    class FakeClient:
        def __init__(self) -> None:
            self.api = SimpleNamespace(observations=FakeObservations())

        def shutdown(self) -> None:
            calls["shutdown"] = True

    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(get_client=FakeClient))

    observations = _collect_from_langfuse(limit=7)

    assert calls["limit"] == 7
    assert calls["fields"] == "core,basic"
    assert calls["shutdown"] is True
    assert observations == [
        {"name": "retrieve", "latency_ms": 125.0},
        {"name": "litellm-acompletion", "latency_ms": 1500.0},
    ]


def test_langfuse_latency_cli_reports_missing_input_file_without_traceback(
    tmp_path: Path,
) -> None:
    cp = _run_script("--from-file", str(tmp_path / "missing.json"))

    combined = cp.stdout + cp.stderr
    assert cp.returncode == 2
    assert "missing.json" in combined
    assert "Traceback" not in combined


def test_cli_rejects_non_positive_limit() -> None:
    cp = _run_script("--limit", "0")

    combined = cp.stdout + cp.stderr
    assert cp.returncode == 2
    assert "--limit" in combined
    assert "positive" in combined.lower()
