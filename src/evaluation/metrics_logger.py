#!/usr/bin/env python3
"""
Production Metrics Logger

Logs RAG search metrics in Prometheus-compatible format for monitoring dashboards.

Features:
    - Prometheus text format export
    - JSON structured logs
    - SLO tracking
    - Anomaly detection

Usage in production:
    from metrics_logger import MetricsLogger

    logger = MetricsLogger()
    logger.log_query(
        query="статья 121 УК",
        engine="dbsf_colbert",
        latency_ms=450,
        precision_at_1=1.0,
        num_results=10
    )

    # Export for Prometheus scraping
    metrics_text = logger.export_prometheus()
    # Write to /metrics endpoint

Integration with monitoring:
    - Prometheus: Scrape /metrics endpoint
    - Grafana: Create dashboards from metrics
    - Alertmanager: Alert on SLO violations
"""

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config_snapshot import get_config_hash


@dataclass
class QueryMetrics:
    """Individual query metrics."""

    query_id: str
    engine: str
    latency_ms: float
    precision_at_1: float
    recall_at_10: float
    num_results: int
    config_hash: str
    timestamp: float = field(default_factory=time.time)
    user_id: str = "anonymous"
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def to_prometheus(self) -> str:
        """
        Export single query metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        return f"""# Query {self.query_id} metrics
rag_query_latency_ms{{engine="{self.engine}",config="{self.config_hash}"}} {self.latency_ms}
rag_precision_at_1{{engine="{self.engine}"}} {self.precision_at_1}
rag_recall_at_10{{engine="{self.engine}"}} {self.recall_at_10}
rag_num_results{{engine="{self.engine}"}} {self.num_results}
"""


class MetricsLogger:
    """
    Production metrics logger with Prometheus export and SLO tracking.

    Attributes:
        log_dir: Directory for JSON log files
        metrics_buffer: In-memory buffer of recent metrics
        aggregated_stats: Rolling window statistics
    """

    def __init__(self, log_dir: str = "evaluation/logs"):
        """
        Initialize metrics logger.

        Args:
            log_dir: Directory to store JSON log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.metrics_buffer: list[QueryMetrics] = []
        self.aggregated_stats: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        # SLO thresholds (from config_snapshot)
        self.slo_thresholds = {
            "p50_latency_ms": 400,
            "p95_latency_ms": 800,
            "p99_latency_ms": 1200,
            "precision_at_1_min": 0.90,
            "recall_at_10_min": 0.95,
        }

    def log_query(
        self,
        query: str,
        engine: str,
        latency_ms: float,
        precision_at_1: float,
        recall_at_10: float = 1.0,
        num_results: int = 10,
        user_id: str = "anonymous",
        session_id: str = "",
    ) -> QueryMetrics:
        """
        Log single query metrics.

        Args:
            query: Search query text
            engine: Search engine name (baseline, hybrid, dbsf_colbert)
            latency_ms: Query latency in milliseconds
            precision_at_1: Precision at rank 1 (0.0 or 1.0)
            recall_at_10: Recall at rank 10 (0.0 or 1.0)
            num_results: Number of results returned
            user_id: User identifier (for user-level analysis)
            session_id: Session identifier (for session tracking)

        Returns:
            QueryMetrics object
        """
        query_id = f"{engine}_{int(time.time() * 1000)}"

        metrics = QueryMetrics(
            query_id=query_id,
            engine=engine,
            latency_ms=latency_ms,
            precision_at_1=precision_at_1,
            recall_at_10=recall_at_10,
            num_results=num_results,
            config_hash=get_config_hash(),
            user_id=user_id,
            session_id=session_id,
        )

        # Add to buffer
        self.metrics_buffer.append(metrics)

        # Update aggregated stats
        self.aggregated_stats[engine]["latency_ms"].append(latency_ms)
        self.aggregated_stats[engine]["precision_at_1"].append(precision_at_1)
        self.aggregated_stats[engine]["recall_at_10"].append(recall_at_10)

        # Write to JSON log file
        self._write_json_log(metrics)

        # Check for anomalies
        self._check_anomalies(metrics)

        return metrics

    def _write_json_log(self, metrics: QueryMetrics) -> None:
        """Write metrics to JSON log file (one per day)."""
        date_str = datetime.fromtimestamp(metrics.timestamp).strftime("%Y-%m-%d")
        log_file = self.log_dir / f"metrics_{date_str}.jsonl"

        with log_file.open("a") as f:
            f.write(metrics.to_json() + "\n")

    def _check_anomalies(self, metrics: QueryMetrics) -> None:
        """Check for anomalous metrics and log warnings."""
        warnings = []

        # Latency anomaly
        if metrics.latency_ms > self.slo_thresholds["p99_latency_ms"]:
            warnings.append(
                f"⚠️  LATENCY ANOMALY: {metrics.latency_ms:.0f}ms "
                f"(threshold: {self.slo_thresholds['p99_latency_ms']}ms)"
            )

        # Quality anomaly
        if metrics.precision_at_1 < self.slo_thresholds["precision_at_1_min"]:
            warnings.append(
                f"⚠️  QUALITY ANOMALY: P@1={metrics.precision_at_1:.1%} "
                f"(threshold: {self.slo_thresholds['precision_at_1_min']:.0%})"
            )

        # Zero results anomaly
        if metrics.num_results == 0:
            warnings.append("⚠️  ZERO RESULTS: No results returned for query")

        if warnings:
            anomaly_log = self.log_dir / "anomalies.log"
            timestamp_str = datetime.fromtimestamp(metrics.timestamp).isoformat()
            with anomaly_log.open("a") as f:
                f.write(f"[{timestamp_str}] {metrics.query_id}\n")
                for warning in warnings:
                    f.write(f"  {warning}\n")
                f.write("\n")

    def export_prometheus(self) -> str:
        """
        Export aggregated metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string for scraping

        Example output:
            # HELP rag_queries_total Total number of queries
            # TYPE rag_queries_total counter
            rag_queries_total{engine="dbsf_colbert"} 1523

            # HELP rag_latency_ms Query latency percentiles
            # TYPE rag_latency_ms summary
            rag_latency_ms{engine="dbsf_colbert",quantile="0.5"} 420.5
            rag_latency_ms{engine="dbsf_colbert",quantile="0.95"} 750.2
        """
        lines = []

        # Header
        lines.append("# Contextual RAG Metrics")
        lines.append(f"# Config: {get_config_hash()}")
        lines.append(f"# Generated: {datetime.now().isoformat()}")
        lines.append("")

        # Per-engine metrics
        for engine, stats in self.aggregated_stats.items():
            # Total queries
            total_queries = len(stats["latency_ms"])
            lines.append("# HELP rag_queries_total Total number of queries")
            lines.append("# TYPE rag_queries_total counter")
            lines.append(f'rag_queries_total{{engine="{engine}"}} {total_queries}')
            lines.append("")

            # Latency percentiles
            if stats["latency_ms"]:
                latencies_sorted = sorted(stats["latency_ms"])
                p50 = latencies_sorted[len(latencies_sorted) // 2]
                p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
                p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]

                lines.append("# HELP rag_latency_ms Query latency in milliseconds")
                lines.append("# TYPE rag_latency_ms summary")
                lines.append(f'rag_latency_ms{{engine="{engine}",quantile="0.5"}} {p50:.1f}')
                lines.append(f'rag_latency_ms{{engine="{engine}",quantile="0.95"}} {p95:.1f}')
                lines.append(f'rag_latency_ms{{engine="{engine}",quantile="0.99"}} {p99:.1f}')
                lines.append("")

            # Precision@1 average
            if stats["precision_at_1"]:
                avg_precision = sum(stats["precision_at_1"]) / len(stats["precision_at_1"])
                lines.append("# HELP rag_precision_at_1 Average precision at rank 1")
                lines.append("# TYPE rag_precision_at_1 gauge")
                lines.append(f'rag_precision_at_1{{engine="{engine}"}} {avg_precision:.4f}')
                lines.append("")

            # Recall@10 average
            if stats["recall_at_10"]:
                avg_recall = sum(stats["recall_at_10"]) / len(stats["recall_at_10"])
                lines.append("# HELP rag_recall_at_10 Average recall at rank 10")
                lines.append("# TYPE rag_recall_at_10 gauge")
                lines.append(f'rag_recall_at_10{{engine="{engine}"}} {avg_recall:.4f}')
                lines.append("")

        # SLO compliance
        lines.append("# HELP rag_slo_violations Number of SLO violations")
        lines.append("# TYPE rag_slo_violations counter")
        for engine in self.aggregated_stats:
            violations = self._count_slo_violations(engine)
            lines.append(f'rag_slo_violations{{engine="{engine}"}} {violations}')

        return "\n".join(lines)

    def _count_slo_violations(self, engine: str) -> int:
        """Count SLO violations for given engine."""
        violations = 0
        stats = self.aggregated_stats[engine]

        # Latency violations
        if stats["latency_ms"]:
            latencies_sorted = sorted(stats["latency_ms"])
            p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
            if p95 > self.slo_thresholds["p95_latency_ms"]:
                violations += 1

        # Quality violations
        if stats["precision_at_1"]:
            avg_precision = sum(stats["precision_at_1"]) / len(stats["precision_at_1"])
            if avg_precision < self.slo_thresholds["precision_at_1_min"]:
                violations += 1

        return violations

    def get_summary(self) -> dict[str, Any]:
        """
        Get summary statistics across all engines.

        Returns:
            Dictionary with summary metrics
        """
        summary = {}

        for engine, stats in self.aggregated_stats.items():
            if not stats["latency_ms"]:
                continue

            latencies_sorted = sorted(stats["latency_ms"])
            p50 = latencies_sorted[len(latencies_sorted) // 2]
            p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]

            avg_precision = sum(stats["precision_at_1"]) / len(stats["precision_at_1"])
            avg_recall = sum(stats["recall_at_10"]) / len(stats["recall_at_10"])

            summary[engine] = {
                "total_queries": len(stats["latency_ms"]),
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "precision_at_1": avg_precision,
                "recall_at_10": avg_recall,
                "slo_violations": self._count_slo_violations(engine),
                "slo_compliant": self._count_slo_violations(engine) == 0,
            }

        return summary

    def print_summary(self) -> None:
        """Print human-readable summary to console."""
        print("=" * 80)
        print("📊 METRICS SUMMARY")
        print("=" * 80)

        summary = self.get_summary()
        if not summary:
            print("\n⚠️  No metrics logged yet")
            return

        for engine, stats in summary.items():
            print(f"\n🔍 Engine: {engine}")
            print(f"   Total Queries: {stats['total_queries']}")
            print("   Latency:")
            print(f"      p50: {stats['latency_p50_ms']:6.0f}ms")
            print(f"      p95: {stats['latency_p95_ms']:6.0f}ms")
            print("   Quality:")
            print(f"      Precision@1: {stats['precision_at_1']:.1%}")
            print(f"      Recall@10:   {stats['recall_at_10']:.1%}")
            print(f"   SLO: {'✅ PASS' if stats['slo_compliant'] else '❌ FAIL'}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    # Example usage
    print("=" * 80)
    print("METRICS LOGGER - Example Usage")
    print("=" * 80)

    logger = MetricsLogger()

    # Simulate 100 queries
    print("\n📊 Simulating 100 queries...")
    import random

    for i in range(100):
        engine = random.choice(["baseline", "dbsf_colbert"])
        latency = random.gauss(650 if engine == "baseline" else 700, 100)
        precision = random.choice([1.0, 1.0, 1.0, 0.0])  # 75% success rate

        logger.log_query(
            query=f"test query {i}",
            engine=engine,
            latency_ms=max(latency, 100),
            precision_at_1=precision,
            num_results=10,
        )

    # Print summary
    logger.print_summary()

    # Export Prometheus metrics
    print("\n" + "=" * 80)
    print("PROMETHEUS EXPORT (first 20 lines)")
    print("=" * 80)
    prom_metrics = logger.export_prometheus()
    print("\n".join(prom_metrics.split("\n")[:20]))
    print("...")

    print("\n" + "=" * 80)
    print(f"✅ Example complete! Check logs in: {logger.log_dir}")
    print("=" * 80)
