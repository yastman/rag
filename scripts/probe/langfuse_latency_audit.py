#!/usr/bin/env python3
"""Langfuse latency audit probe (#2179).

Aggregates per-stage observation latencies from recent traces into a
sanitized p50/p95 report so the operator can identify speed
bottlenecks (retrieve, cache, checkpoint, LLM).

Implementation strategy:

- The aggregator (:func:`aggregate_latencies`) is pure: it consumes a
  list of dicts ``{"name": str, "latency_ms": float | int | None}`` and
  returns a :class:`LatencyReport`. Pure aggregation is unit-testable
  against synthetic inputs.
- The CLI fetches recent traces via the existing
  :mod:`scripts.e2e.langfuse_latest_trace_audit` infrastructure when
  available, or accepts a JSON file via ``--from-file`` for
  deterministic / CI use.
- Buckets are matched by name prefix/keyword: ``retrieve``, ``cache``,
  ``checkpoint``, ``llm``, with a fallback ``other`` bucket that is
  only reported when non-empty.

Refs #2179.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_LATENCY_BUCKETS: tuple[str, ...] = ("retrieve", "cache", "checkpoint", "llm")

_BUCKET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "retrieve": ("retrieve", "search", "rerank", "colbert", "rrf"),
    "cache": ("cache",),
    "checkpoint": ("checkpoint", "checkpointer"),
    "llm": (
        "llm",
        "litellm",
        "openai",
        "anthropic",
        "claude",
        "groq",
        "ollama",
        "deepseek",
        "completion",
    ),
}


def classify_observation_name(name: str) -> str:
    """Classify an observation name into a bucket via keyword match."""
    lowered = name.lower()
    for bucket, keywords in _BUCKET_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return bucket
    return "other"


@dataclass(frozen=True)
class BucketStats:
    bucket: str
    count: int
    p50: float
    p95: float
    p99: float


@dataclass(frozen=True)
class LatencyReport:
    buckets: dict[str, BucketStats]
    missing_stages: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = ["Langfuse latency audit (#2179)"]
        lines.append(f"  {'bucket':<12}  {'count':>5}  {'p50':>8}  {'p95':>8}  {'p99':>8}  (ms)")
        for stats in self.buckets.values():
            lines.append(
                f"  {stats.bucket:<12}  {stats.count:>5}  "
                f"{stats.p50:>8.0f}  {stats.p95:>8.0f}  {stats.p99:>8.0f}"
            )
        if self.missing_stages:
            lines.append(f"  missing stages: {', '.join(self.missing_stages)}")
        return "\n".join(lines)


def _percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile, returns 0 for empty input."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return float(ordered[rank - 1])


def aggregate_latencies(observations: Iterable[Mapping[str, object]]) -> LatencyReport:
    """Aggregate observation latencies into per-bucket stats."""
    samples: dict[str, list[float]] = {bucket: [] for bucket in DEFAULT_LATENCY_BUCKETS}
    samples["other"] = []

    for obs in observations:
        name_obj = obs.get("name")
        if not isinstance(name_obj, str):
            continue
        latency_obj = obs.get("latency_ms")
        if latency_obj is None:
            continue
        try:
            latency = float(latency_obj)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        bucket = classify_observation_name(name_obj)
        samples.setdefault(bucket, []).append(latency)

    bucket_stats: dict[str, BucketStats] = {}
    for bucket in DEFAULT_LATENCY_BUCKETS:
        s = samples.get(bucket, [])
        bucket_stats[bucket] = BucketStats(
            bucket=bucket,
            count=len(s),
            p50=_percentile(s, 50),
            p95=_percentile(s, 95),
            p99=_percentile(s, 99),
        )
    # Surface 'other' only when it has data so reports stay focused.
    if samples.get("other"):
        s = samples["other"]
        bucket_stats["other"] = BucketStats(
            bucket="other",
            count=len(s),
            p50=_percentile(s, 50),
            p95=_percentile(s, 95),
            p99=_percentile(s, 99),
        )

    missing = [bucket for bucket in DEFAULT_LATENCY_BUCKETS if bucket_stats[bucket].count == 0]
    return LatencyReport(buckets=bucket_stats, missing_stages=missing)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_observations_from_file(path: Path) -> list[dict[str, object]]:
    """Read a list of observation dicts from a JSON file.

    Accepts either a top-level list or a top-level object with a
    ``"observations"`` key.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [obs for obs in payload if isinstance(obs, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("observations"), list):
        return [obs for obs in payload["observations"] if isinstance(obs, dict)]
    return []


def _collect_from_langfuse(limit: int) -> list[dict[str, object]]:
    """Best-effort live collection via the Langfuse SDK; returns [] on errors."""
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        client = Langfuse()
        traces = client.api.trace.list(limit=limit)
    except Exception:
        return []
    out: list[dict[str, object]] = []
    for trace in getattr(traces, "data", []) or []:
        for obs in getattr(trace, "observations", []) or []:
            name = getattr(obs, "name", None)
            latency = getattr(obs, "latency", None)
            if isinstance(name, str) and latency is not None:
                # Langfuse SDK exposes latency as seconds (float). Convert to ms.
                try:
                    latency_ms = float(latency) * 1000.0
                except (TypeError, ValueError):
                    continue
                out.append({"name": name, "latency_ms": latency_ms})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="Read observations from a JSON file (deterministic / CI mode).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of recent traces to inspect when reading from Langfuse.",
    )
    args = parser.parse_args(argv)

    if args.from_file is not None:
        observations = _load_observations_from_file(args.from_file)
    else:
        observations = _collect_from_langfuse(args.limit)

    report = aggregate_latencies(observations)
    print(report.render())
    return 1 if report.missing_stages else 0


if __name__ == "__main__":
    sys.exit(main())
