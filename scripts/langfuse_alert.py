#!/usr/bin/env python3
"""Langfuse alert script: hourly Tier-1 alerts + morning digest (#758).

Modes:
  --mode hourly   Check last hour: dislike rate > 15%, faithfulness < 0.5 → Telegram alert
  --mode digest   Morning summary: dislike rate, latency p95, cache hit rate, top reasons

Alerting Tiers:
  Tier 1 — Immediate: dislike rate > 15%/hour (min 20 samples)
  Tier 1 — Immediate: judge_faithfulness < 0.5/hour
  Tier 2 — Daily trends: morning digest

Usage:
    uv run python -m scripts.langfuse_alert --mode hourly
    uv run python -m scripts.langfuse_alert --mode digest
    uv run python -m scripts.langfuse_alert --mode hourly --hours 1
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from dotenv import load_dotenv
from langfuse import Langfuse


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alert thresholds
# ---------------------------------------------------------------------------

DISLIKE_RATE_THRESHOLD = 0.15  # Tier 1: > 15% dislike
FAITHFULNESS_THRESHOLD = 0.5  # Tier 1: < 0.5 faithfulness
MIN_SAMPLES = 20  # Minimum samples required before triggering

# ---------------------------------------------------------------------------
# Metrics query helpers
# ---------------------------------------------------------------------------


def build_metrics_query(
    score_name: str,
    from_ts: str,
    to_ts: str,
    aggregations: list[str] | None = None,
) -> str:
    """Build Langfuse Metrics API JSON query for a single score.

    Args:
        score_name: Langfuse score name (e.g. "user_feedback").
        from_ts: ISO8601 start timestamp.
        to_ts: ISO8601 end timestamp.
        aggregations: List of aggregations (default: ["avg", "p95", "count"]).

    Returns:
        JSON string suitable for lf.api.metrics.metrics(query=...).
    """
    if aggregations is None:
        aggregations = ["avg", "p95", "count"]

    metrics: list[dict[str, str]] = []
    for agg in aggregations:
        if agg == "count":
            metrics.append({"measure": "count", "aggregation": "count"})
        else:
            metrics.append({"measure": "value", "aggregation": agg})

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
    aggregations: list[str] | None = None,
) -> dict[str, Any]:
    """Query Langfuse Metrics API for a single score's aggregates.

    Returns:
        Dict with keys like "value_avg", "value_p95", "count_count".
        Empty dict on error or no data.
    """
    query_str = build_metrics_query(score_name, from_ts, to_ts, aggregations)
    try:
        result = lf.api.metrics.metrics(query=query_str)
        data = getattr(result, "data", [])
        if data:
            row = data[0]
            parsed: dict[str, Any] = {}
            if hasattr(row, "__dict__"):
                for key, val in row.__dict__.items():
                    if val is not None:
                        try:
                            parsed[key] = float(val)
                        except (TypeError, ValueError):
                            parsed[key] = val
            elif isinstance(row, dict):
                for k, v in row.items():
                    if v is not None:
                        try:
                            parsed[k] = float(v)
                        except (TypeError, ValueError):
                            parsed[k] = v
            return parsed
        return {}
    except Exception as e:
        logger.warning("Metrics API query failed for %s: %s", score_name, e)
        return {}


def get_top_dislike_reasons(
    api: Any,
    from_ts: str,
    to_ts: str,
    top_n: int = 5,
) -> list[tuple[str, int]]:
    """Fetch top dislike reasons from user_feedback_reason categorical scores.

    Args:
        api: Langfuse low-level API client (langfuse.api).
        from_ts: ISO8601 start timestamp.
        to_ts: ISO8601 end timestamp.
        top_n: Number of top reasons to return.

    Returns:
        List of (reason_label, count) sorted by count descending.
    """
    try:
        response = api.scores.get(
            name="user_feedback_reason",
            from_timestamp=from_ts,
            to_timestamp=to_ts,
        )
        scores = getattr(response, "data", [])
        counter: Counter[str] = Counter()
        for score in scores:
            label = getattr(score, "string_value", None)
            if label:
                counter[label] += 1
        return counter.most_common(top_n)
    except Exception as e:
        logger.warning("Failed to fetch dislike reasons: %s", e)
        return []


# ---------------------------------------------------------------------------
# Dislike rate computation
# ---------------------------------------------------------------------------


def compute_dislike_rate(metrics: dict[str, Any]) -> tuple[float, int]:
    """Compute dislike rate from user_feedback score metrics.

    user_feedback: 0.0 = dislike, 1.0 = like.
    dislike_rate = 1.0 - avg_like.

    Args:
        metrics: Dict from query_score_metrics with keys like "value_avg", "count_count".

    Returns:
        (dislike_rate, total_count). Returns (0.0, 0) if no data.
    """
    avg_like = metrics.get("value_avg")
    raw_count = metrics.get("count_count", 0)
    count = int(raw_count) if raw_count else 0

    if avg_like is None or count == 0:
        return 0.0, 0

    return 1.0 - float(avg_like), count


# ---------------------------------------------------------------------------
# Alert checking
# ---------------------------------------------------------------------------


def check_hourly_alerts(
    user_feedback_metrics: dict[str, Any],
    faithfulness_metrics: dict[str, Any],
    *,
    dislike_threshold: float = DISLIKE_RATE_THRESHOLD,
    min_samples: int = MIN_SAMPLES,
    faithfulness_threshold: float = FAITHFULNESS_THRESHOLD,
) -> list[dict[str, Any]]:
    """Check hourly metrics against Tier-1 alert thresholds.

    Args:
        user_feedback_metrics: Metrics dict for "user_feedback" score.
        faithfulness_metrics: Metrics dict for "judge_faithfulness" score.
        dislike_threshold: Dislike rate threshold (default 0.15 = 15%).
        min_samples: Minimum feedback samples required (default 20).
        faithfulness_threshold: Faithfulness score threshold (default 0.5).

    Returns:
        List of fired alert dicts. Empty list if all metrics are healthy.
    """
    alerts: list[dict[str, Any]] = []

    # Tier 1: Dislike rate
    dislike_rate, count = compute_dislike_rate(user_feedback_metrics)
    if count >= min_samples and dislike_rate > dislike_threshold:
        alerts.append(
            {
                "tier": 1,
                "type": "dislike_rate",
                "value": dislike_rate,
                "threshold": dislike_threshold,
                "count": count,
            }
        )

    # Tier 1: Faithfulness
    faith_avg = faithfulness_metrics.get("value_avg")
    faith_raw = faithfulness_metrics.get("count_count", 0)
    faith_count = int(faith_raw) if faith_raw else 0
    if (
        faith_avg is not None
        and faith_count >= min_samples
        and float(faith_avg) < faithfulness_threshold
    ):
        alerts.append(
            {
                "tier": 1,
                "type": "judge_faithfulness",
                "value": float(faith_avg),
                "threshold": faithfulness_threshold,
                "count": faith_count,
            }
        )

    return alerts


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def format_alert_message(alert: dict[str, Any]) -> str:
    """Format a Tier-1 Telegram alert message.

    Args:
        alert: Alert dict from check_hourly_alerts().

    Returns:
        Formatted alert message string.
    """
    alert_type = alert.get("type", "unknown")
    value = alert.get("value", 0.0)
    threshold = alert.get("threshold", 0.0)
    count = alert.get("count", 0)

    if alert_type == "dislike_rate":
        return (
            f"🚨 ALERT Tier 1: High dislike rate\n"
            f"Dislike rate: {value:.0%} (threshold: {threshold:.0%})\n"
            f"Samples: {count}\n"
            f"Action: Review recent responses for quality issues."
        )
    if alert_type == "judge_faithfulness":
        return (
            f"🚨 ALERT Tier 1: Low faithfulness score\n"
            f"judge_faithfulness avg: {value:.2f} (threshold: {threshold})\n"
            f"Samples: {count}\n"
            f"Action: Check for hallucinations in recent answers."
        )
    return (
        f"🚨 ALERT Tier 1: {alert_type}\n"
        f"Value: {value:.3f} (threshold: {threshold})\n"
        f"Samples: {count}"
    )


def format_digest_message(
    user_feedback_metrics: dict[str, Any],
    faithfulness_metrics: dict[str, Any],
    latency_metrics: dict[str, Any],
    cache_metrics: dict[str, Any],
    top_reasons: list[tuple[str, int]],
) -> str:
    """Format daily digest Telegram message.

    Args:
        user_feedback_metrics: Metrics dict for "user_feedback" score.
        faithfulness_metrics: Metrics dict for "judge_faithfulness" score.
        latency_metrics: Metrics dict for "latency_total_ms" score.
        cache_metrics: Metrics dict for "semantic_cache_hit" score.
        top_reasons: List of (reason_label, count) from get_top_dislike_reasons().

    Returns:
        Formatted digest message string.
    """
    dislike_rate, feedback_count = compute_dislike_rate(user_feedback_metrics)
    faith_avg = faithfulness_metrics.get("value_avg")
    latency_p95 = latency_metrics.get("value_p95")
    cache_hit_rate = cache_metrics.get("value_avg")

    lines = [
        "📊 Daily RAG Digest",
        f"Date: {datetime.now(UTC).strftime('%Y-%m-%d')}",
        "",
        "── Feedback ──",
    ]

    if feedback_count > 0:
        like_rate = 1.0 - dislike_rate
        lines.append(f"  Like rate:    {like_rate:.0%}  |  Dislike rate: {dislike_rate:.0%}")
        lines.append(f"  Total feedback: {feedback_count}")
    else:
        lines.append("  No feedback data")

    lines.append("")
    lines.append("── Quality ──")
    if faith_avg is not None:
        lines.append(f"  Faithfulness avg: {float(faith_avg):.2f}")
    else:
        lines.append("  Faithfulness: no data")

    lines.append("")
    lines.append("── Latency ──")
    if latency_p95 is not None:
        lines.append(f"  p95 latency: {latency_p95:.0f} ms")
    else:
        lines.append("  Latency p95: no data")

    lines.append("")
    lines.append("── Cache ──")
    if cache_hit_rate is not None:
        lines.append(f"  Semantic cache hit rate: {float(cache_hit_rate):.0%}")
    else:
        lines.append("  Cache hit rate: no data")

    if top_reasons:
        lines.append("")
        lines.append("── Top dislike reasons ──")
        for label, cnt in top_reasons:
            lines.append(f"  {label}: {cnt}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram delivery
# ---------------------------------------------------------------------------


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Send message to Telegram admin chat via Bot API.

    Args:
        token: Telegram bot token.
        chat_id: Target chat ID (e.g. "-100123456789").
        text: Message text (will be HTML-escaped and sent as plain text).

    Returns:
        True on success, False on failure.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    safe_text = html.escape(text)
    try:
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": safe_text, "parse_mode": "HTML"},
            timeout=10.0,
        )
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            return True
        logger.warning("Telegram API error: %s", data.get("description", "unknown"))
        return False
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def run_hourly(lf: Langfuse, token: str, chat_id: str, hours: int = 1) -> int:
    """Run hourly alert check. Returns number of alerts fired."""
    to_dt = datetime.now(UTC)
    from_dt = to_dt - timedelta(hours=hours)
    from_ts = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_ts = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("Hourly check: %s — %s", from_ts, to_ts)

    feedback_metrics = query_score_metrics(lf, "user_feedback", from_ts, to_ts, ["avg", "count"])
    faith_metrics = query_score_metrics(lf, "judge_faithfulness", from_ts, to_ts, ["avg", "count"])

    alerts = check_hourly_alerts(feedback_metrics, faith_metrics)

    if not alerts:
        logger.info("No Tier-1 alerts fired.")
        return 0

    for alert in alerts:
        msg = format_alert_message(alert)
        ok = send_telegram_message(token, chat_id, msg)
        if ok:
            logger.info("Alert sent: %s", alert["type"])
        else:
            logger.error("Failed to send alert: %s", alert["type"])

    return len(alerts)


def run_digest(lf: Langfuse, token: str, chat_id: str, hours: int = 24) -> bool:
    """Run daily digest. Queries last N hours and sends summary.

    Returns:
        True if digest was sent successfully, False on delivery failure.
    """
    to_dt = datetime.now(UTC)
    from_dt = to_dt - timedelta(hours=hours)
    from_ts = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_ts = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("Daily digest: %s — %s", from_ts, to_ts)

    feedback_metrics = query_score_metrics(lf, "user_feedback", from_ts, to_ts, ["avg", "count"])
    faith_metrics = query_score_metrics(lf, "judge_faithfulness", from_ts, to_ts, ["avg", "count"])
    latency_metrics = query_score_metrics(
        lf, "latency_total_ms", from_ts, to_ts, ["p95", "avg", "count"]
    )
    cache_metrics = query_score_metrics(lf, "semantic_cache_hit", from_ts, to_ts, ["avg", "count"])
    top_reasons = get_top_dislike_reasons(lf.api, from_ts, to_ts, top_n=5)

    msg = format_digest_message(
        feedback_metrics, faith_metrics, latency_metrics, cache_metrics, top_reasons
    )

    ok = send_telegram_message(token, chat_id, msg)
    if ok:
        logger.info("Daily digest sent.")
    else:
        logger.error("Failed to send daily digest.")
    return ok


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Langfuse alert script (#758)")
    parser.add_argument(
        "--mode",
        choices=["hourly", "digest"],
        default="hourly",
        help="Alert mode: 'hourly' (Tier-1 checks) or 'digest' (daily summary)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Lookback window in hours (default: 1 for hourly, 24 for digest)",
    )
    args = parser.parse_args()

    # Resolve lookback window
    hours = args.hours
    if hours is None:
        hours = 1 if args.mode == "hourly" else 24

    # Required env vars (see .env.example: ALERTING section)
    token = os.environ.get("TELEGRAM_ALERTING_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALERTING_CHAT_ID", "")

    if not token or not chat_id:
        logger.error(
            "Missing required env vars: TELEGRAM_ALERTING_BOT_TOKEN and TELEGRAM_ALERTING_CHAT_ID"
        )
        sys.exit(1)

    try:
        lf = Langfuse()
    except Exception as e:
        logger.error("Failed to initialize Langfuse client: %s", e)
        sys.exit(1)

    try:
        if args.mode == "hourly":
            alert_count = run_hourly(lf, token, chat_id, hours=hours)
            if alert_count > 0:
                sys.exit(2)  # Non-zero exit for monitoring systems
        else:
            sent = run_digest(lf, token, chat_id, hours=hours)
            if not sent:
                sys.exit(1)
    finally:
        lf.flush()


if __name__ == "__main__":
    main()
