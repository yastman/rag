"""Tests for scripts/langfuse_alert.py (TDD — RED first).

Tests: dislike rate computation, alert thresholds, Telegram sending, digest formatting.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _load_module():
    """Load langfuse_alert as a module without executing main()."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "langfuse_alert.py"
    spec = importlib.util.spec_from_file_location("langfuse_alert", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# compute_dislike_rate
# ---------------------------------------------------------------------------


def test_compute_dislike_rate_from_avg_like():
    """avg_like=0.8 means 20% dislike rate, count=50."""
    module = _load_module()
    rate, count = module.compute_dislike_rate({"value_avg": 0.8, "count_count": 50.0})
    assert abs(rate - 0.2) < 1e-9
    assert count == 50


def test_compute_dislike_rate_all_dislikes():
    """avg_like=0.0 means 100% dislike rate."""
    module = _load_module()
    rate, count = module.compute_dislike_rate({"value_avg": 0.0, "count_count": 25.0})
    assert abs(rate - 1.0) < 1e-9
    assert count == 25


def test_compute_dislike_rate_no_data():
    """Empty metrics return zero rate and zero count."""
    module = _load_module()
    rate, count = module.compute_dislike_rate({})
    assert rate == 0.0
    assert count == 0


def test_compute_dislike_rate_zero_count():
    """Zero count returns (0.0, 0) even if avg is present."""
    module = _load_module()
    rate, count = module.compute_dislike_rate({"value_avg": 0.5, "count_count": 0.0})
    assert rate == 0.0
    assert count == 0


# ---------------------------------------------------------------------------
# check_hourly_alerts — Tier 1
# ---------------------------------------------------------------------------


def test_check_hourly_alerts_fires_on_high_dislike_rate():
    """Dislike rate > 15% with >= 20 samples triggers Tier 1 alert."""
    module = _load_module()
    # avg_like=0.8 → 20% dislike, 25 samples
    feedback_metrics = {"value_avg": 0.8, "count_count": 25.0}
    faith_metrics = {"value_avg": 0.7, "count_count": 25.0}

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)

    assert len(alerts) == 1
    assert alerts[0]["type"] == "dislike_rate"
    assert alerts[0]["tier"] == 1
    assert abs(alerts[0]["value"] - 0.2) < 1e-9


def test_check_hourly_alerts_not_fired_below_dislike_threshold():
    """Dislike rate <= 15% does not trigger alert."""
    module = _load_module()
    # avg_like=0.9 → 10% dislike, 30 samples
    feedback_metrics = {"value_avg": 0.9, "count_count": 30.0}
    faith_metrics = {"value_avg": 0.7, "count_count": 30.0}

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)
    dislike_alerts = [a for a in alerts if a["type"] == "dislike_rate"]
    assert dislike_alerts == []


def test_check_hourly_alerts_not_fired_insufficient_samples():
    """Dislike rate > 15% but < 20 samples does NOT trigger alert."""
    module = _load_module()
    # avg_like=0.7 → 30% dislike but only 5 samples
    feedback_metrics = {"value_avg": 0.7, "count_count": 5.0}
    faith_metrics = {"value_avg": 0.7, "count_count": 5.0}

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)
    dislike_alerts = [a for a in alerts if a["type"] == "dislike_rate"]
    assert dislike_alerts == []


def test_check_hourly_alerts_fires_on_low_faithfulness():
    """judge_faithfulness avg < 0.5 with sufficient samples triggers Tier 1 alert."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.95, "count_count": 30.0}
    faith_metrics = {"value_avg": 0.4, "count_count": 25.0}

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)

    faith_alerts = [a for a in alerts if a["type"] == "judge_faithfulness"]
    assert len(faith_alerts) == 1
    assert faith_alerts[0]["tier"] == 1
    assert abs(faith_alerts[0]["value"] - 0.4) < 1e-9


def test_check_hourly_alerts_not_fired_on_good_metrics():
    """No alert when all metrics within thresholds."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.92, "count_count": 50.0}
    faith_metrics = {"value_avg": 0.75, "count_count": 50.0}

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)
    assert alerts == []


def test_check_hourly_alerts_both_tiers_fire():
    """Both dislike rate and faithfulness can fire simultaneously."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.7, "count_count": 30.0}  # 30% dislike
    faith_metrics = {"value_avg": 0.3, "count_count": 30.0}  # 0.3 faithfulness

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)
    assert len(alerts) == 2
    types = {a["type"] for a in alerts}
    assert types == {"dislike_rate", "judge_faithfulness"}


def test_check_hourly_alerts_no_data_no_alert():
    """Empty metrics produce no alerts."""
    module = _load_module()
    alerts = module.check_hourly_alerts({}, {})
    assert alerts == []


# ---------------------------------------------------------------------------
# format_alert_message
# ---------------------------------------------------------------------------


def test_format_alert_message_dislike_contains_key_info():
    """Alert message for dislike_rate includes rate, count, threshold."""
    module = _load_module()
    alert = {
        "tier": 1,
        "type": "dislike_rate",
        "value": 0.22,
        "threshold": 0.15,
        "count": 25,
    }
    msg = module.format_alert_message(alert)
    assert "22%" in msg or "0.22" in msg
    assert "15%" in msg or "0.15" in msg
    assert "25" in msg


def test_format_alert_message_faithfulness_contains_key_info():
    """Alert message for judge_faithfulness includes score and threshold."""
    module = _load_module()
    alert = {
        "tier": 1,
        "type": "judge_faithfulness",
        "value": 0.38,
        "threshold": 0.5,
        "count": 20,
    }
    msg = module.format_alert_message(alert)
    assert "faithfulness" in msg.lower() or "0.38" in msg
    assert "0.5" in msg or "50%" in msg


def test_format_alert_message_is_non_empty_string():
    """format_alert_message always returns a non-empty string."""
    module = _load_module()
    alert = {"tier": 1, "type": "dislike_rate", "value": 0.2, "threshold": 0.15, "count": 20}
    msg = module.format_alert_message(alert)
    assert isinstance(msg, str)
    assert len(msg) > 10


# ---------------------------------------------------------------------------
# format_digest_message
# ---------------------------------------------------------------------------


def test_format_digest_message_includes_dislike_rate():
    """Daily digest message includes dislike rate percentage."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.85, "count_count": 120.0}
    faith_metrics = {"value_avg": 0.78, "count_count": 120.0}
    latency_metrics = {"value_p95": 3200.0, "count_count": 120.0}
    cache_metrics = {"value_avg": 0.65, "count_count": 120.0}
    top_reasons: list[tuple[str, int]] = [("irrelevant", 15), ("incomplete", 8)]

    msg = module.format_digest_message(
        feedback_metrics, faith_metrics, latency_metrics, cache_metrics, top_reasons
    )
    # 15% dislike (1 - 0.85)
    assert "15%" in msg or "0.15" in msg


def test_format_digest_message_includes_latency_p95():
    """Daily digest message includes latency p95 in ms."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.9, "count_count": 50.0}
    faith_metrics = {"value_avg": 0.8, "count_count": 50.0}
    latency_metrics = {"value_p95": 4500.0, "count_count": 50.0}
    cache_metrics = {"value_avg": 0.7, "count_count": 50.0}

    msg = module.format_digest_message(
        feedback_metrics, faith_metrics, latency_metrics, cache_metrics, []
    )
    assert "4500" in msg or "4.5" in msg


def test_format_digest_message_includes_cache_hit_rate():
    """Daily digest message includes cache hit rate."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.9, "count_count": 50.0}
    faith_metrics = {"value_avg": 0.8, "count_count": 50.0}
    latency_metrics = {"value_p95": 2000.0, "count_count": 50.0}
    cache_metrics = {"value_avg": 0.42, "count_count": 50.0}

    msg = module.format_digest_message(
        feedback_metrics, faith_metrics, latency_metrics, cache_metrics, []
    )
    assert "42%" in msg or "0.42" in msg


def test_format_digest_message_includes_top_reasons():
    """Daily digest message includes top dislike reason labels."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.8, "count_count": 80.0}
    faith_metrics = {"value_avg": 0.75, "count_count": 80.0}
    latency_metrics = {"value_p95": 2000.0, "count_count": 80.0}
    cache_metrics = {"value_avg": 0.6, "count_count": 80.0}
    top_reasons: list[tuple[str, int]] = [("irrelevant", 10), ("incomplete", 5)]

    msg = module.format_digest_message(
        feedback_metrics, faith_metrics, latency_metrics, cache_metrics, top_reasons
    )
    assert "irrelevant" in msg


def test_format_digest_message_handles_empty_data():
    """format_digest_message handles empty metrics without crashing."""
    module = _load_module()
    msg = module.format_digest_message({}, {}, {}, {}, [])
    assert isinstance(msg, str)
    assert len(msg) > 0


# ---------------------------------------------------------------------------
# send_telegram_message
# ---------------------------------------------------------------------------


def test_send_telegram_message_success():
    """Returns True when Telegram API responds 200 with ok=true."""
    module = _load_module()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = module.send_telegram_message(
            token="test_token", chat_id="-100123456", text="Test alert"
        )

    assert result is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "sendMessage" in call_args[0][0]


def test_send_telegram_message_api_error():
    """Returns False when Telegram API responds with ok=false."""
    module = _load_module()

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"ok": False, "description": "Bad Request"}

    with patch("httpx.post", return_value=mock_response):
        result = module.send_telegram_message(
            token="test_token", chat_id="-100123456", text="Test alert"
        )

    assert result is False


def test_send_telegram_message_network_error():
    """Returns False on network exception."""
    module = _load_module()

    with patch("httpx.post", side_effect=Exception("Connection refused")):
        result = module.send_telegram_message(
            token="test_token", chat_id="-100123456", text="Test alert"
        )

    assert result is False


def test_send_telegram_message_posts_correct_url():
    """Uses correct Telegram Bot API URL with token."""
    module = _load_module()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}

    with patch("httpx.post", return_value=mock_response) as mock_post:
        module.send_telegram_message(token="abc:123", chat_id="-999", text="hello")

    url = mock_post.call_args[0][0]
    assert "abc:123" in url
    assert "sendMessage" in url


# ---------------------------------------------------------------------------
# build_metrics_query
# ---------------------------------------------------------------------------


def test_build_metrics_query_returns_valid_json():
    """build_metrics_query returns a JSON-serializable string."""
    module = _load_module()
    query_str = module.build_metrics_query(
        score_name="user_feedback",
        from_ts="2026-03-03T08:00:00Z",
        to_ts="2026-03-03T09:00:00Z",
    )
    query = json.loads(query_str)
    assert isinstance(query, dict)


def test_build_metrics_query_includes_score_filter():
    """build_metrics_query filters by score name."""
    module = _load_module()
    query_str = module.build_metrics_query(
        score_name="user_feedback",
        from_ts="2026-03-03T08:00:00Z",
        to_ts="2026-03-03T09:00:00Z",
    )
    query = json.loads(query_str)
    filters = query.get("filters", [])
    name_filters = [f for f in filters if f.get("column") == "name"]
    assert len(name_filters) == 1
    assert name_filters[0]["value"] == "user_feedback"


def test_build_metrics_query_includes_time_range():
    """build_metrics_query includes from/to timestamps."""
    module = _load_module()
    from_ts = "2026-03-03T08:00:00Z"
    to_ts = "2026-03-03T09:00:00Z"
    query_str = module.build_metrics_query("latency_total_ms", from_ts, to_ts)
    query = json.loads(query_str)
    assert query["fromTimestamp"] == from_ts
    assert query["toTimestamp"] == to_ts


def test_build_metrics_query_default_aggregations_include_avg_and_count():
    """Default aggregations include avg and count."""
    module = _load_module()
    query_str = module.build_metrics_query(
        "user_feedback",
        "2026-03-03T08:00:00Z",
        "2026-03-03T09:00:00Z",
    )
    query = json.loads(query_str)
    aggregations = {m["aggregation"] for m in query.get("metrics", [])}
    assert "avg" in aggregations
    assert "count" in aggregations


def test_build_metrics_query_p95_aggregation():
    """Latency query can include p95 aggregation."""
    module = _load_module()
    query_str = module.build_metrics_query(
        "latency_total_ms",
        "2026-03-03T08:00:00Z",
        "2026-03-03T09:00:00Z",
        aggregations=["p95", "avg", "count"],
    )
    query = json.loads(query_str)
    aggregations = {m["aggregation"] for m in query.get("metrics", [])}
    assert "p95" in aggregations


# ---------------------------------------------------------------------------
# get_top_dislike_reasons
# ---------------------------------------------------------------------------


def test_get_top_dislike_reasons_returns_sorted_list():
    """Returns list of (reason, count) sorted by count descending."""
    module = _load_module()

    score1 = MagicMock()
    score1.string_value = "irrelevant"
    score1.value = None

    score2 = MagicMock()
    score2.string_value = "incomplete"
    score2.value = None

    score3 = MagicMock()
    score3.string_value = "irrelevant"
    score3.value = None

    mock_api = MagicMock()
    mock_api.scores.get.return_value.data = [score1, score2, score3]
    mock_api.scores.get.return_value.meta.total_items = 3

    result = module.get_top_dislike_reasons(
        api=mock_api,
        from_ts="2026-03-03T00:00:00Z",
        to_ts="2026-03-03T23:59:59Z",
        top_n=3,
    )

    assert result[0] == ("irrelevant", 2)
    assert result[1] == ("incomplete", 1)


def test_get_top_dislike_reasons_returns_empty_on_no_data():
    """Returns empty list when no dislike reason scores found."""
    module = _load_module()
    mock_api = MagicMock()
    mock_api.scores.get.return_value.data = []

    result = module.get_top_dislike_reasons(
        api=mock_api,
        from_ts="2026-03-03T00:00:00Z",
        to_ts="2026-03-03T23:59:59Z",
    )
    assert result == []


def test_get_top_dislike_reasons_limits_to_top_n():
    """Returns at most top_n reasons."""
    module = _load_module()

    scores = []
    for reason in ["a", "b", "c", "d", "e"]:
        s = MagicMock()
        s.string_value = reason
        s.value = None
        scores.append(s)

    mock_api = MagicMock()
    mock_api.scores.get.return_value.data = scores

    result = module.get_top_dislike_reasons(
        api=mock_api,
        from_ts="2026-03-03T00:00:00Z",
        to_ts="2026-03-03T23:59:59Z",
        top_n=3,
    )
    assert len(result) <= 3


# ---------------------------------------------------------------------------
# check_hourly_alerts — min_samples guard on faithfulness
# ---------------------------------------------------------------------------


def test_check_hourly_alerts_faithfulness_not_fired_insufficient_samples():
    """Low faithfulness but < 20 samples does NOT trigger alert."""
    module = _load_module()
    feedback_metrics = {"value_avg": 0.95, "count_count": 5.0}
    faith_metrics = {"value_avg": 0.3, "count_count": 5.0}  # below 0.5 but only 5 samples

    alerts = module.check_hourly_alerts(feedback_metrics, faith_metrics)
    faith_alerts = [a for a in alerts if a["type"] == "judge_faithfulness"]
    assert faith_alerts == []


# ---------------------------------------------------------------------------
# run_hourly / run_digest integration (mocked Langfuse + Telegram)
# ---------------------------------------------------------------------------


def _make_mock_lf(feedback_avg: float = 0.95, faith_avg: float = 0.8, count: float = 30.0):
    """Build a mock Langfuse object whose metrics API returns predictable data."""
    mock_lf = MagicMock()

    def fake_metrics(query: str):
        q = json.loads(query)
        name_filter = next(
            (f["value"] for f in q.get("filters", []) if f["column"] == "name"), None
        )
        # Use dicts so query_score_metrics takes the isinstance(row, dict) branch
        if name_filter == "user_feedback":
            row: dict = {"value_avg": feedback_avg, "count_count": count}
        elif name_filter == "judge_faithfulness":
            row = {"value_avg": faith_avg, "count_count": count}
        else:
            row = {"value_avg": 0.6, "value_p95": 2000.0, "count_count": count}
        result = MagicMock()
        result.data = [row]
        return result

    mock_lf.api.metrics.metrics.side_effect = fake_metrics
    mock_lf.api.scores.get.return_value.data = []
    return mock_lf


def test_run_hourly_returns_zero_when_no_alerts():
    """run_hourly returns 0 when metrics are healthy and sends no messages."""
    module = _load_module()
    mock_lf = _make_mock_lf(feedback_avg=0.92, faith_avg=0.8, count=30.0)

    with patch("httpx.post") as mock_post:
        result = module.run_hourly(mock_lf, token="tok", chat_id="-100", hours=1)

    assert result == 0
    mock_post.assert_not_called()


def test_run_hourly_returns_alert_count_and_sends_message():
    """run_hourly returns alert count and sends Telegram message when dislike > 15%."""
    module = _load_module()
    # avg_like=0.7 → 30% dislike, 30 samples
    mock_lf = _make_mock_lf(feedback_avg=0.7, faith_avg=0.8, count=30.0)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}

    with patch("httpx.post", return_value=mock_response):
        result = module.run_hourly(mock_lf, token="tok", chat_id="-100", hours=1)

    assert result == 1


def test_run_digest_returns_true_on_success():
    """run_digest returns True when digest is sent successfully."""
    module = _load_module()
    mock_lf = _make_mock_lf()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}

    with patch("httpx.post", return_value=mock_response):
        result = module.run_digest(mock_lf, token="tok", chat_id="-100", hours=24)

    assert result is True


def test_run_digest_returns_false_on_send_failure():
    """run_digest returns False when Telegram delivery fails."""
    module = _load_module()
    mock_lf = _make_mock_lf()

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"ok": False, "description": "Bad Request"}

    with patch("httpx.post", return_value=mock_response):
        result = module.run_digest(mock_lf, token="tok", chat_id="-100", hours=24)

    assert result is False
