#!/usr/bin/env python3
"""Langfuse Metrics API: LLM latency breakdown report (#147).

Queries Langfuse scores-numeric view for latency breakdown metrics
(llm_ttft_ms, llm_decode_ms, llm_queue_ms, llm_tps, llm_timeout)
and checks thresholds. Outputs human-readable report or JSON.

Usage:
    uv run python scripts/setup_langfuse_dashboards.py
    uv run python scripts/setup_langfuse_dashboards.py --hours 24 --json
    uv run python scripts/setup_langfuse_dashboards.py --check-alerts
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from langfuse import Langfuse


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alert thresholds (from design doc)
# ---------------------------------------------------------------------------

ALERT_THRESHOLDS: dict[str, list[dict[str, Any]]] = {
    "llm_ttft_ms": [
        {"aggregation": "p95", "threshold": 2000, "severity": "WARNING", "label": "TTFT p95 high"},
        {
            "aggregation": "p95",
            "threshold": 5000,
            "severity": "CRITICAL",
            "label": "TTFT p95 critical",
        },
    ],
    "llm_decode_ms": [
        {
            "aggregation": "p95",
            "threshold": 3000,
            "severity": "WARNING",
            "label": "Decode p95 high",
        },
    ],
    "llm_queue_ms": [
        {"aggregation": "p95", "threshold": 1000, "severity": "WARNING", "label": "Queue p95 high"},
        {
            "aggregation": "p95",
            "threshold": 3000,
            "severity": "CRITICAL",
            "label": "Queue p95 critical",
        },
    ],
    "llm_timeout": [
        {
            "aggregation": "avg",
            "threshold": 0.05,
            "severity": "CRITICAL",
            "label": "Timeout rate > 5%",
        },
    ],
    "llm_tps": [
        {
            "aggregation": "p50",
            "threshold": 20,
            "severity": "WARNING",
            "label": "TPS p50 low",
            "below": True,
        },
    ],
    "llm_stream_recovery": [
        {
            "aggregation": "avg",
            "threshold": 0.10,
            "severity": "WARNING",
            "label": "Stream recovery > 10%",
        },
    ],
}

# Scores to query and their aggregations
LATENCY_SCORES = [
    "llm_ttft_ms",
    "llm_decode_ms",
    "llm_queue_ms",
    "llm_tps",
    "llm_timeout",
    "streaming_enabled",
    "llm_stream_recovery",
]


def _safe_float(val: Any) -> Any:
    """Convert to float if numeric, otherwise return as-is."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def _build_query(
    score_name: str,
    from_ts: str,
    to_ts: str,
    aggregations: list[str] | None = None,
) -> str:
    """Build Metrics API JSON query for a single score."""
    if aggregations is None:
        aggregations = ["p50", "p95", "avg", "max"]

    metrics = [{"measure": "value", "aggregation": agg} for agg in aggregations]
    metrics.append({"measure": "count", "aggregation": "count"})

    query = {
        "view": "scores-numeric",
        "metrics": metrics,
        "dimensions": [],
        "filters": [
            {"column": "name", "operator": "=", "value": score_name, "type": "string"},
        ],
        "fromTimestamp": from_ts,
        "toTimestamp": to_ts,
    }
    return json.dumps(query)


def query_score_metrics(
    lf: Langfuse,
    score_name: str,
    from_ts: str,
    to_ts: str,
) -> dict[str, Any]:
    """Query Langfuse Metrics API for a single score's aggregates."""
    query_str = _build_query(score_name, from_ts, to_ts)
    try:
        result = lf.api.metrics.metrics(query=query_str)
        data = getattr(result, "data", [])
        if data and len(data) > 0:
            row = data[0]
            # Extract values from response row
            parsed: dict[str, Any] = {}
            if hasattr(row, "__dict__"):
                for key, val in row.__dict__.items():
                    if val is not None:
                        parsed[key] = _safe_float(val)
            elif isinstance(row, dict):
                parsed = {k: _safe_float(v) for k, v in row.items() if v is not None}
            return parsed
        return {}
    except Exception as e:
        logger.warning("Metrics API query failed for %s: %s", score_name, e)
        return {"error": str(e)}


def check_alerts(metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Check metrics against alert thresholds. Returns list of fired alerts."""
    fired: list[dict[str, Any]] = []

    for score_name, thresholds in ALERT_THRESHOLDS.items():
        score_data = metrics.get(score_name, {})
        if not score_data or "error" in score_data:
            continue

        for rule in thresholds:
            agg_key = f"value_{rule['aggregation']}"
            actual = score_data.get(agg_key)
            if actual is None:
                continue

            actual_float = float(actual)
            is_below = rule.get("below", False)

            if is_below:
                triggered = actual_float < rule["threshold"]
            else:
                triggered = actual_float > rule["threshold"]

            if triggered:
                fired.append(
                    {
                        "score": score_name,
                        "label": rule["label"],
                        "severity": rule["severity"],
                        "aggregation": rule["aggregation"],
                        "threshold": rule["threshold"],
                        "actual": actual_float,
                        "direction": "below" if is_below else "above",
                    }
                )

    return fired


def has_query_errors(metrics: dict[str, dict[str, Any]]) -> bool:
    """Return True when any score query failed."""
    return any(
        isinstance(score_data, dict) and "error" in score_data for score_data in metrics.values()
    )


def format_report(
    metrics: dict[str, dict[str, Any]],
    alerts: list[dict[str, Any]],
    from_ts: str,
    to_ts: str,
) -> str:
    """Format human-readable latency breakdown report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("LLM Latency Breakdown Report (#147)")
    lines.append(f"Period: {from_ts} — {to_ts}")
    lines.append("=" * 60)
    lines.append("")

    lines.append("Score               | Count | p50      | p95      | Avg      | Max")
    lines.append("-" * 80)

    for score_name in LATENCY_SCORES:
        data = metrics.get(score_name, {})
        if not data or "error" in data:
            lines.append(f"{score_name:<20}| {'N/A (no data or error)':>57}")
            continue

        count = data.get("count_count", data.get("count", "?"))
        p50 = data.get("value_p50", "—")
        p95 = data.get("value_p95", "—")
        avg = data.get("value_avg", "—")
        mx = data.get("value_max", "—")

        def fmt(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.1f}"
            return str(v)

        lines.append(
            f"{score_name:<20}| {fmt(count):>5} | {fmt(p50):>8} | {fmt(p95):>8} | {fmt(avg):>8} | {fmt(mx):>8}"
        )

    lines.append("")

    if alerts:
        lines.append("ALERTS FIRED:")
        for a in alerts:
            lines.append(
                f"  [{a['severity']}] {a['label']}: {a['actual']:.1f} "
                f"({a['direction']} threshold {a['threshold']})"
            )
    else:
        lines.append("No alerts fired.")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Langfuse LLM latency breakdown report")
    parser.add_argument(
        "--hours", type=int, default=24, help="Lookback window in hours (default: 24)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--check-alerts",
        action="store_true",
        help="Check alert thresholds/query errors and exit with code 1 on failure",
    )
    args = parser.parse_args()

    to_dt = datetime.now(UTC)
    from_dt = to_dt - timedelta(hours=args.hours)
    from_ts = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_ts = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("Querying Langfuse Metrics API: %s — %s", from_ts, to_ts)

    try:
        lf = Langfuse()
    except Exception as e:
        logger.error("Failed to initialize Langfuse client: %s", e)
        sys.exit(1)

    metrics: dict[str, dict[str, Any]] = {}
    for score_name in LATENCY_SCORES:
        metrics[score_name] = query_score_metrics(lf, score_name, from_ts, to_ts)

    alerts = check_alerts(metrics)

    if args.json:
        output = {
            "period": {"from": from_ts, "to": to_ts, "hours": args.hours},
            "metrics": metrics,
            "alerts": alerts,
            "alerts_fired": len(alerts),
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_report(metrics, alerts, from_ts, to_ts))

    if args.check_alerts:
        if has_query_errors(metrics):
            logger.error("One or more Metrics API queries failed")
            sys.exit(1)

        if alerts:
            critical = [a for a in alerts if a["severity"] == "CRITICAL"]
            if critical:
                logger.error("%d CRITICAL alert(s) fired", len(critical))
                sys.exit(1)
            logger.warning("%d WARNING alert(s) fired", len(alerts))

    lf.flush()


if __name__ == "__main__":
    main()
