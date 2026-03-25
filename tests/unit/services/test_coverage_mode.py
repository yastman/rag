from __future__ import annotations

from telegram_bot.graph.state import make_initial_state
from telegram_bot.services.coverage_mode import cap_results_per_doc, detect_coverage_mode


def test_detect_coverage_mode_matches_enumeration_query() -> None:
    decision = detect_coverage_mode(
        "какие еще есть виды внж в болгарии? напиши полный список всех вариантов"
    )

    assert decision.needs_coverage is True
    assert decision.reason.startswith("regex:")


def test_detect_coverage_mode_ignores_normal_specific_question() -> None:
    decision = detect_coverage_mode("сколько стоит студия в Несебре?")

    assert decision.needs_coverage is False
    assert decision.reason is None


def test_cap_results_per_doc_preserves_order_and_limits_duplicates() -> None:
    docs = [
        {"id": "1", "metadata": {"doc_id": "a"}, "score": 0.95},
        {"id": "2", "metadata": {"doc_id": "a"}, "score": 0.92},
        {"id": "3", "metadata": {"doc_id": "a"}, "score": 0.91},
        {"id": "4", "metadata": {"doc_id": "b"}, "score": 0.80},
    ]

    result = cap_results_per_doc(docs, max_per_doc=2)

    assert [doc["id"] for doc in result] == ["1", "2", "4"]


def test_make_initial_state_defaults_needs_coverage_false() -> None:
    state = make_initial_state(user_id=1, session_id="s1", query="обычный вопрос")

    assert state["needs_coverage"] is False
