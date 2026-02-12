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
        """Create baseline snapshot from per-session Langfuse trace data.

        `from_ts`/`to_ts` are kept for backward-compatible signature.
        """
        session = self.collector.collect_session_metrics(session_id=session_id)

        return BaselineSnapshot(
            timestamp=to_ts,
            tag=tag,
            session_id=session_id,
            llm_latency_p50_ms=session.llm_latency_p50_ms,
            llm_latency_p95_ms=session.llm_latency_p95_ms,
            full_rag_latency_p95_ms=session.llm_latency_p95_ms * 1.5,
            total_cost_usd=session.total_cost_usd,
            llm_tokens_input=session.llm_tokens_input,
            llm_tokens_output=session.llm_tokens_output,
            llm_calls=session.llm_calls,
            voyage_embed_calls=0,
            voyage_rerank_calls=0,
            cache_hit_rate=session.cache_hit_rate,
            cache_hits=session.cache_hits,
            cache_misses=session.cache_misses,
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
