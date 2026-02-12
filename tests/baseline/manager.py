"""Baseline management via Langfuse sessions/tags."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .collector import LangfuseMetricsCollector


@dataclass
class BaselineSnapshot:
    """Snapshot of metrics for comparison."""

    # Metadata
    timestamp: datetime
    tag: str
    session_id: str

    # Latency (milliseconds)
    llm_latency_p50_ms: float
    llm_latency_p95_ms: float
    full_rag_latency_p95_ms: float

    # Cost
    total_cost_usd: float
    llm_tokens_input: int
    llm_tokens_output: int

    # Call counts
    llm_calls: int
    voyage_embed_calls: int
    voyage_rerank_calls: int

    # Cache effectiveness
    cache_hit_rate: float
    cache_hits: int
    cache_misses: int


class BaselineManager:
    """Manage baselines stored as Langfuse sessions/tags.

    Baselines are identified by session_id in Langfuse.
    Comparison uses thresholds from thresholds.yaml.
    """

    def __init__(
        self,
        collector: LangfuseMetricsCollector,
        thresholds_path: Path | None = None,
    ):
        """Initialize manager.

        Args:
            collector: LangfuseMetricsCollector instance
            thresholds_path: Path to thresholds.yaml (default: same dir)
        """
        self.collector = collector

        if thresholds_path is None:
            thresholds_path = Path(__file__).parent / "thresholds.yaml"

        with open(thresholds_path) as f:
            self.thresholds = yaml.safe_load(f)

    def create_snapshot(
        self,
        tag: str,
        session_id: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> BaselineSnapshot:
        """Create baseline snapshot from Langfuse data.

        .. deprecated:: 2.0
            Use collector.collect_session_metrics() + cli._metrics_to_snapshot() instead.

        Args:
            tag: Human-readable tag (e.g., "smoke-v1.0.0")
            session_id: Langfuse session ID
            from_ts: Start timestamp
            to_ts: End timestamp

        Returns:
            BaselineSnapshot with aggregated metrics
        """
        import warnings

        warnings.warn(
            "create_snapshot is deprecated. Use collect_session_metrics() instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Get daily metrics for cost/tokens
        daily = self.collector.get_daily_metrics(from_ts, to_ts)

        # Get latency metrics
        latency = self.collector.get_latency_metrics(from_ts, to_ts)

        # Get cache metrics
        cache = self.collector.get_cache_metrics(from_ts, to_ts, session_id)

        # Aggregate daily metrics
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        total_traces = 0

        for day in daily.get("data", []):
            total_cost += day.get("totalCost", 0)
            total_traces += day.get("countTraces", 0)
            for usage in day.get("usage", []):
                total_input_tokens += usage.get("inputUsage", 0)
                total_output_tokens += usage.get("outputUsage", 0)

        # Extract latency percentiles
        llm_p50 = 0.0
        llm_p95 = 0.0

        for item in latency.get("data", []):
            llm_p50 = float(item.get("latency_p50", 0))
            llm_p95 = float(item.get("latency_p95", 0))
            break  # Take first model's metrics

        # Get operation counts
        voyage_embed_count = self.collector.get_trace_count(from_ts, to_ts, "voyage-embed")
        voyage_rerank_count = self.collector.get_trace_count(from_ts, to_ts, "voyage-rerank")

        return BaselineSnapshot(
            timestamp=to_ts,
            tag=tag,
            session_id=session_id,
            llm_latency_p50_ms=llm_p50,
            llm_latency_p95_ms=llm_p95,
            full_rag_latency_p95_ms=llm_p95 * 1.5,  # Estimate
            total_cost_usd=total_cost,
            llm_tokens_input=total_input_tokens,
            llm_tokens_output=total_output_tokens,
            llm_calls=total_traces,
            voyage_embed_calls=voyage_embed_count,
            voyage_rerank_calls=voyage_rerank_count,
            cache_hit_rate=cache["hit_rate"],
            cache_hits=cache["hits"],
            cache_misses=cache["misses"],
        )

    def compare(
        self,
        current: BaselineSnapshot,
        baseline: BaselineSnapshot,
        custom_thresholds: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str]]:
        """Compare current metrics against baseline.

        Args:
            current: Current run snapshot
            baseline: Baseline snapshot to compare against
            custom_thresholds: Override default thresholds

        Returns:
            Tuple of (passed, list of regression messages)
        """
        thresholds = custom_thresholds or self.thresholds
        regressions: list[str] = []

        # Latency checks
        latency_thresholds = thresholds.get("latency", {})

        llm_factor = latency_thresholds.get("llm_p95_factor", 1.2)
        if current.llm_latency_p95_ms > baseline.llm_latency_p95_ms * llm_factor:
            pct = (current.llm_latency_p95_ms / baseline.llm_latency_p95_ms - 1) * 100
            regressions.append(
                f"LLM p95 latency regression: {current.llm_latency_p95_ms:.0f}ms "
                f"vs baseline {baseline.llm_latency_p95_ms:.0f}ms (+{pct:.1f}%)"
            )

        rag_factor = latency_thresholds.get("full_rag_p95_factor", 1.2)
        if current.full_rag_latency_p95_ms > baseline.full_rag_latency_p95_ms * rag_factor:
            pct = (current.full_rag_latency_p95_ms / baseline.full_rag_latency_p95_ms - 1) * 100
            regressions.append(
                f"Full RAG p95 latency regression: {current.full_rag_latency_p95_ms:.0f}ms "
                f"vs baseline {baseline.full_rag_latency_p95_ms:.0f}ms (+{pct:.1f}%)"
            )

        # Cost checks
        cost_thresholds = thresholds.get("cost", {})

        cost_factor = cost_thresholds.get("total_factor", 1.1)
        if (
            baseline.total_cost_usd > 0
            and current.total_cost_usd > baseline.total_cost_usd * cost_factor
        ):
            pct = (current.total_cost_usd / baseline.total_cost_usd - 1) * 100
            regressions.append(
                f"Cost regression: ${current.total_cost_usd:.4f} "
                f"vs baseline ${baseline.total_cost_usd:.4f} (+{pct:.1f}%)"
            )

        # Cache checks
        cache_thresholds = thresholds.get("cache", {})

        cache_drop = cache_thresholds.get("hit_rate_min_drop", 0.1)
        if current.cache_hit_rate < baseline.cache_hit_rate - cache_drop:
            drop = baseline.cache_hit_rate - current.cache_hit_rate
            regressions.append(
                f"Cache hit rate drop: {current.cache_hit_rate:.1%} "
                f"vs baseline {baseline.cache_hit_rate:.1%} (-{drop:.1%})"
            )

        # Call count checks
        calls_thresholds = thresholds.get("calls", {})

        llm_calls_factor = calls_thresholds.get("llm_factor", 1.05)
        if baseline.llm_calls > 0 and current.llm_calls > baseline.llm_calls * llm_calls_factor:
            pct = (current.llm_calls / baseline.llm_calls - 1) * 100
            regressions.append(
                f"LLM calls increase: {current.llm_calls} "
                f"vs baseline {baseline.llm_calls} (+{pct:.1f}%)"
            )

        return len(regressions) == 0, regressions
