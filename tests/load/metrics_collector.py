# tests/load/metrics_collector.py
"""Metrics collection and analysis for load tests."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .thresholds import MIN_CACHE_HIT_RATE, REGRESSION_THRESHOLD, THRESHOLDS


@dataclass
class LoadMetrics:
    """Collected metrics from load test run."""

    # Latency samples (ms)
    routing_latencies: list[float] = field(default_factory=list)
    cache_hit_latencies: list[float] = field(default_factory=list)
    qdrant_latencies: list[float] = field(default_factory=list)
    full_rag_latencies: list[float] = field(default_factory=list)
    ttft_latencies: list[float] = field(default_factory=list)  # Only if streaming

    # Counters
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0

    # Redis stats snapshots
    redis_stats_start: dict = field(default_factory=dict)
    redis_stats_end: dict = field(default_factory=dict)
    redis_stats_timeseries: list[dict] = field(default_factory=list)

    def record_routing(self, latency_ms: float):
        self.routing_latencies.append(latency_ms)

    def record_cache_hit(self, latency_ms: float):
        self.cache_hit_latencies.append(latency_ms)
        self.cache_hits += 1

    def record_cache_miss(self):
        self.cache_misses += 1

    def record_qdrant(self, latency_ms: float):
        self.qdrant_latencies.append(latency_ms)

    def record_full_rag(self, latency_ms: float):
        self.full_rag_latencies.append(latency_ms)
        self.total_requests += 1

    def record_ttft(self, latency_ms: float):
        """Record time-to-first-token (only if streaming is used)."""
        self.ttft_latencies.append(latency_ms)

    def record_error(self):
        self.errors += 1
        self.total_requests += 1

    def record_redis_snapshot(self, stats: dict):
        """Record Redis INFO stats snapshot."""
        self.redis_stats_timeseries.append(
            {
                "timestamp": time.time(),
                **stats,
            }
        )


def percentile(values: list[float], p: int) -> float:
    """Calculate percentile. Returns 0 if no values."""
    if not values:
        return 0.0
    return float(np.percentile(values, p))


@dataclass
class MetricsResult:
    """Analyzed metrics result."""

    routing_p95: float
    cache_hit_p95: float
    qdrant_p95: float
    full_rag_p95: float
    ttft_p95: float  # 0 if not measured

    cache_hit_rate: float
    error_rate: float

    warnings: list[str]
    failures: list[str]
    passed: bool


def analyze_metrics(
    metrics: LoadMetrics,
    baseline: dict | None = None,
    require_ttft: bool = False,  # If True, fail when TTFT not measured
) -> MetricsResult:
    """Analyze collected metrics against thresholds."""
    warnings = []
    failures = []

    # Calculate p95 values
    routing_p95 = percentile(metrics.routing_latencies, 95)
    cache_hit_p95 = percentile(metrics.cache_hit_latencies, 95)
    qdrant_p95 = percentile(metrics.qdrant_latencies, 95)
    full_rag_p95 = percentile(metrics.full_rag_latencies, 95)
    ttft_p95 = percentile(metrics.ttft_latencies, 95)

    # Calculate rates
    total_cache_ops = metrics.cache_hits + metrics.cache_misses
    cache_hit_rate = metrics.cache_hits / total_cache_ops if total_cache_ops > 0 else 0.0
    error_rate = metrics.errors / metrics.total_requests if metrics.total_requests > 0 else 0.0

    # Check absolute thresholds
    checks = [
        ("routing", routing_p95, THRESHOLDS["routing"]),
        ("cache_hit", cache_hit_p95, THRESHOLDS["cache_hit"]),
        ("qdrant", qdrant_p95, THRESHOLDS["qdrant"]),
        ("full_rag", full_rag_p95, THRESHOLDS["full_rag"]),
    ]

    # TTFT check: mandatory if require_ttft=True
    if require_ttft and not metrics.ttft_latencies:
        failures.append("TTFT required but not measured (streaming not used?)")
    elif metrics.ttft_latencies:
        checks.append(("ttft", ttft_p95, THRESHOLDS["ttft"]))

    for name, value, threshold in checks:
        if value > 0:  # Only check if we have data
            if value > threshold.fail_ms:
                failures.append(f"{name} p95 {value:.0f}ms > fail {threshold.fail_ms}ms")
            elif value > threshold.warn_ms:
                warnings.append(f"{name} p95 {value:.0f}ms > warn {threshold.warn_ms}ms")

    # Check cache hit rate (only if we have cache operations)
    if total_cache_ops > 0 and cache_hit_rate < MIN_CACHE_HIT_RATE:
        failures.append(f"cache hit rate {cache_hit_rate:.1%} < min {MIN_CACHE_HIT_RATE:.1%}")

    # Check regression against baseline
    if baseline:
        p95_values = {
            "routing": routing_p95,
            "cache_hit": cache_hit_p95,
            "qdrant": qdrant_p95,
            "full_rag": full_rag_p95,
        }
        if metrics.ttft_latencies:
            p95_values["ttft"] = ttft_p95

        for name, current in p95_values.items():
            if (
                name in baseline
                and current > 0
                and baseline[name] > 0
                and current > baseline[name] * REGRESSION_THRESHOLD
            ):
                failures.append(
                    f"{name} regression: {current:.0f}ms vs baseline {baseline[name]:.0f}ms "
                    f"(+{((current / baseline[name]) - 1) * 100:.0f}%)"
                )

    return MetricsResult(
        routing_p95=routing_p95,
        cache_hit_p95=cache_hit_p95,
        qdrant_p95=qdrant_p95,
        full_rag_p95=full_rag_p95,
        ttft_p95=ttft_p95,
        cache_hit_rate=cache_hit_rate,
        error_rate=error_rate,
        warnings=warnings,
        failures=failures,
        passed=len(failures) == 0,
    )


def load_baseline(path: Path) -> dict | None:
    """Load baseline from JSON file."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_baseline(path: Path, result: MetricsResult):
    """Save current p95 as new baseline."""
    baseline = {
        "routing": result.routing_p95,
        "cache_hit": result.cache_hit_p95,
        "qdrant": result.qdrant_p95,
        "full_rag": result.full_rag_p95,
        "ttft": result.ttft_p95,
        "timestamp": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)


def format_report(
    result: MetricsResult,
    metrics: LoadMetrics,
    duration_sec: float,
    chat_count: int,
) -> str:
    """Format metrics report for output."""
    lines = [
        "=" * 60,
        "LOAD TEST RESULTS",
        f"Duration: {duration_sec / 60:.1f} min | Chats: {chat_count} | "
        f"Requests: {metrics.total_requests}",
        "=" * 60,
        "",
        "LATENCY (p95):",
    ]

    p95_checks = [
        ("routing", result.routing_p95, THRESHOLDS["routing"]),
        ("cache_hit", result.cache_hit_p95, THRESHOLDS["cache_hit"]),
        ("qdrant", result.qdrant_p95, THRESHOLDS["qdrant"]),
        ("full_rag", result.full_rag_p95, THRESHOLDS["full_rag"]),
    ]

    # Only show TTFT if measured
    if result.ttft_p95 > 0:
        p95_checks.append(("ttft", result.ttft_p95, THRESHOLDS["ttft"]))

    for name, value, threshold in p95_checks:
        if value > 0:
            if value <= threshold.warn_ms:
                status = "✓"
            elif value <= threshold.fail_ms:
                status = "⚠"
            else:
                status = "✗"
            lines.append(
                f"  {name:12}: {value:6.0f}ms {status} "
                f"(warn: {threshold.warn_ms}ms, fail: {threshold.fail_ms}ms)"
            )
        else:
            lines.append(f"  {name:12}: (not measured)")

    cache_status = "✓" if result.cache_hit_rate >= MIN_CACHE_HIT_RATE else "✗"
    lines.extend(
        [
            "",
            "CACHE:",
            f"  hit_rate:   {result.cache_hit_rate:.0%}   {cache_status} "
            f"(min: {MIN_CACHE_HIT_RATE:.0%})",
            "",
        ]
    )

    if result.warnings:
        lines.append("WARNINGS:")
        for w in result.warnings:
            lines.append(f"  ⚠ {w}")
        lines.append("")

    if result.failures:
        lines.append("FAILURES:")
        for f in result.failures:
            lines.append(f"  ✗ {f}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(f"{'PASSED' if result.passed else 'FAILED'}")
    lines.append("=" * 60)

    return "\n".join(lines)
