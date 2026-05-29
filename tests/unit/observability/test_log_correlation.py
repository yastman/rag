"""Unit tests for log<->trace correlation evaluation (#2255).

Covers the subtlety that the JSON formatter (telegram_bot/logging_config.py)
renames the OTEL LogRecord attributes ``otelTraceID``/``otelSpanID`` to the
emitted JSON keys ``trace_id``/``span_id`` and treats the string ``"0"`` (the
OTEL "no active trace" sentinel) as absence. The evaluator must accept either
spelling and reject the sentinel.
"""

from __future__ import annotations

from scripts.log_correlation import (
    LogCorrelation,
    check_log_correlation,
    evaluate_log_correlation,
    get_correlation_value,
    has_log_correlation_failure,
    load_log_records,
    record_has_fields,
    summarize_log_correlation,
)


REQUIRED = ("otelTraceID", "otelSpanID")


# --- field extraction --------------------------------------------------------


def test_get_correlation_value_accepts_emitted_json_keys() -> None:
    rec = {"trace_id": "abc123", "span_id": "def456"}
    assert get_correlation_value(rec, "otelTraceID") == "abc123"
    assert get_correlation_value(rec, "otelSpanID") == "def456"


def test_get_correlation_value_accepts_raw_otel_attr_keys() -> None:
    rec = {"otelTraceID": "abc123", "otelSpanID": "def456"}
    assert get_correlation_value(rec, "otelTraceID") == "abc123"


def test_zero_sentinel_is_treated_as_absent() -> None:
    rec = {"trace_id": "0", "span_id": ""}
    assert get_correlation_value(rec, "otelTraceID") is None
    assert get_correlation_value(rec, "otelSpanID") is None


def test_record_has_fields_true_and_false() -> None:
    assert record_has_fields({"trace_id": "t", "span_id": "s"}, REQUIRED)
    assert not record_has_fields({"trace_id": "t"}, REQUIRED)


# --- evaluation --------------------------------------------------------------


def test_ok_when_records_carry_fields_and_match_expected() -> None:
    recs = [{"trace_id": "t1", "span_id": "s1"}, {"trace_id": "t1", "span_id": "s2"}]
    result = evaluate_log_correlation("telegram_text_rag", REQUIRED, recs, expected_trace_id="t1")
    assert isinstance(result, LogCorrelation)
    assert result.status == "ok"
    assert result.ok is True
    assert result.correlated == 2


def test_incomplete_when_logs_present_but_uncorrelated() -> None:
    recs = [{"message": "startup"}, {"trace_id": "0"}]
    result = evaluate_log_correlation("telegram_text_rag", REQUIRED, recs)
    assert result.status == "incomplete"
    assert result.ok is False
    assert result.correlated == 0


def test_mismatch_when_trace_id_differs_from_expected() -> None:
    recs = [{"trace_id": "WRONG", "span_id": "s1"}]
    result = evaluate_log_correlation("telegram_text_rag", REQUIRED, recs, expected_trace_id="t1")
    assert result.status == "mismatch"
    assert result.ok is False
    assert result.trace_id_mismatches == 1


def test_unavailable_when_no_logs() -> None:
    result = evaluate_log_correlation("telegram_text_rag", REQUIRED, [], expected_trace_id="t1")
    assert result.status == "unavailable"
    assert result.ok is False


# --- gate semantics ----------------------------------------------------------


def test_has_failure_only_on_mismatch() -> None:
    mismatch = evaluate_log_correlation("f", REQUIRED, [{"trace_id": "x", "span_id": "y"}], "t1")
    incomplete = evaluate_log_correlation("f", REQUIRED, [{"message": "m"}])
    unavailable = evaluate_log_correlation("f", REQUIRED, [])
    assert has_log_correlation_failure([mismatch]) is True
    assert has_log_correlation_failure([incomplete, unavailable]) is False


def test_summarize_mentions_flow_and_status() -> None:
    result = evaluate_log_correlation("telegram_text_rag", REQUIRED, [])
    text = summarize_log_correlation([result])
    assert "telegram_text_rag" in text
    assert "unavailable" in text.lower()


# --- flow-driven check + log loader ------------------------------------------


def test_check_log_correlation_uses_flow_required_log_fields() -> None:
    flows = {
        "telegram_text_rag": {
            "root_family": "telegram-rag-query",
            "required_log_fields": ["otelTraceID", "otelSpanID"],
        }
    }
    recs = [{"trace_id": "t1", "span_id": "s1"}]
    results = check_log_correlation(flows, recs, expected_trace_ids={"telegram_text_rag": "t1"})
    assert len(results) == 1
    assert results[0].status == "ok"


def test_check_log_correlation_unavailable_without_logs() -> None:
    flows = {"telegram_text_rag": {"required_log_fields": list(REQUIRED)}}
    results = check_log_correlation(flows, [])
    assert results[0].status == "unavailable"


def test_check_log_correlation_does_not_cross_match_shared_log_dump() -> None:
    flows = {
        "telegram_text_rag": {
            "root_family": "telegram-rag-query",
            "required_log_fields": list(REQUIRED),
        },
        "voice_rag_api": {
            "root_family": "voice-session",
            "required_log_fields": list(REQUIRED),
        },
    }
    records = [
        {"trace_id": "trace-text", "span_id": "span-text"},
        {"trace_id": "trace-voice", "span_id": "span-voice"},
    ]
    results = check_log_correlation(
        flows,
        records,
        expected_trace_ids={
            "telegram_text_rag": "trace-text",
            "voice_rag_api": "trace-voice",
        },
    )
    assert {r.flow_name: r.status for r in results} == {
        "telegram_text_rag": "ok",
        "voice_rag_api": "ok",
    }
    assert all(r.trace_id_mismatches == 0 for r in results)


def test_check_log_correlation_keeps_explicit_flow_mismatch() -> None:
    flows = {
        "telegram_text_rag": {
            "root_family": "telegram-rag-query",
            "required_log_fields": list(REQUIRED),
        },
    }
    records = [{"flow_name": "telegram_text_rag", "trace_id": "wrong", "span_id": "span-1"}]
    results = check_log_correlation(
        flows,
        records,
        expected_trace_ids={"telegram_text_rag": "trace-text"},
    )
    assert results[0].status == "mismatch"
    assert results[0].trace_id_mismatches == 1


def test_load_log_records_parses_ndjson_and_skips_bad_lines(tmp_path) -> None:
    p = tmp_path / "logs.ndjson"
    p.write_text(
        '{"trace_id": "t1", "span_id": "s1"}\nnot-json\n{"message": "ok"}\n',
        encoding="utf-8",
    )
    records = load_log_records(p)
    assert len(records) == 2
    assert records[0]["trace_id"] == "t1"


def test_load_log_records_missing_source_returns_empty(tmp_path) -> None:
    assert load_log_records(tmp_path / "absent.ndjson") == []
    assert load_log_records(None) == []
