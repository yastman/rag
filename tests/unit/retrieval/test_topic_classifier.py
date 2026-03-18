"""Tests for retrieval topic/doc-type helpers."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.retrieval.topic_classifier import (
    DocType,
    TopicLabel,
    classify_chunk_topic,
    classify_doc_type,
    detect_score_gap,
    get_query_topic_hint,
)
from telegram_bot.services.grounding_policy import get_grounding_mode


def test_classify_chunk_topic_finance() -> None:
    assert classify_chunk_topic("Рассрочка 0% и первый взнос 5%") == TopicLabel.FINANCE


def test_classify_chunk_topic_legal() -> None:
    assert classify_chunk_topic("Документы для ВНЖ в Болгарии") == TopicLabel.LEGAL


def test_classify_doc_type_for_services_yaml() -> None:
    assert classify_doc_type("telegram_bot/config/services.yaml", "application/yaml") == DocType.FAQ


def test_classify_doc_type_for_audio_transcript() -> None:
    assert classify_doc_type("calls/transcript-1.txt", "audio/mpeg") == DocType.TRANSCRIPT


def test_get_query_topic_hint_returns_none_for_generic_query() -> None:
    assert get_query_topic_hint("какая погода") is None


def test_get_query_topic_hint_finance() -> None:
    assert get_query_topic_hint("какие есть варианты рассрочки") == TopicLabel.FINANCE


def test_get_query_topic_hint_legal() -> None:
    assert get_query_topic_hint("какие документы нужны для внж") == TopicLabel.LEGAL


def test_get_query_topic_hint_legal_english() -> None:
    assert get_query_topic_hint("bulgaria residence permit categories") == TopicLabel.LEGAL


def test_get_query_topic_hint_returns_none_for_property_query() -> None:
    assert get_query_topic_hint("подбери квартиру у моря") is None


def test_grounding_mode_is_strict_for_legal_query() -> None:
    assert get_grounding_mode(query_type="FAQ", topic_hint="legal") == "strict"


def test_grounding_mode_is_normal_for_generic_property_query() -> None:
    assert get_grounding_mode(query_type="GENERAL", topic_hint=None) == "normal"


def test_detect_score_gap_marks_dense_cluster_not_confident() -> None:
    result = detect_score_gap([0.0164, 0.0160, 0.0158])

    assert result["confident"] is False


def test_detect_score_gap_marks_clear_winner_confident() -> None:
    result = detect_score_gap([0.62, 0.40, 0.39])

    assert result["confident"] is True


def test_query_topic_hints_match_retrieval_quality_fixture() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "retrieval"
        / "retrieval_quality_cases.yaml"
    )
    cases = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(cases, list)

    topic_by_label = {label.value: label for label in TopicLabel}
    for case in cases:
        query = case["query"]
        expected_topic = topic_by_label[case["expected_topic"]]
        assert get_query_topic_hint(query) == expected_topic
