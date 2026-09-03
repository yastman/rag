"""Unit tests for src/runtime/generation/policy.py pure helpers (#3222).

The bot-local generation shims (``telegram_bot/services/generation/*``) were
removed in #3222; the citation-stripping behaviour they exercised through the
wrapper is pinned here directly against the canonical implementation.
"""

from __future__ import annotations

import pytest

from src.runtime.generation.policy import _build_fallback_response, _sanitize_response_text


class TestSanitizeResponseText:
    """Citation-artifact stripping (sources disabled)."""

    def test_strips_inline_citations_and_trailing_suffixes(self) -> None:
        answer = "Потребуется также счёт в болгарском банке 1.\nИ подтверждение дохода [2]."
        assert _sanitize_response_text(answer, sources_enabled=False) == (
            "Потребуется также счёт в болгарском банке\nИ подтверждение дохода."
        )

    def test_keeps_citations_when_sources_enabled(self) -> None:
        answer = "Ответ [1] с источником [2]."
        assert _sanitize_response_text(answer, sources_enabled=True) == answer

    def test_strips_object_labels_when_sources_disabled(self) -> None:
        answer = "[Объект 1] Студия в Sunny Beach стоит 80 000€."
        cleaned = _sanitize_response_text(answer, sources_enabled=False)
        assert "[Объект 1]" not in cleaned
        assert "Студия в Sunny Beach" in cleaned

    def test_keeps_numbered_list_prefix(self) -> None:
        answer = "1. Первая строка\n2. Вторая строка"
        assert _sanitize_response_text(answer, sources_enabled=False) == answer

    def test_empty_answer_returned_as_is(self) -> None:
        assert _sanitize_response_text("", sources_enabled=False) == ""


class TestBuildFallbackResponse:
    """Document-derived fallback text when the LLM is unavailable."""

    def test_no_documents_returns_apology(self) -> None:
        text = _build_fallback_response([])
        assert "временно недоступен" in text

    def test_documents_produce_numbered_summary(self) -> None:
        docs = [
            {
                "text": "Студия у моря",
                "score": 0.9,
                "metadata": {
                    "title": "Студия Sunny Beach",
                    "price": 80000,
                    "city": "Солнечный берег",
                },
            }
        ]
        text = _build_fallback_response(docs)
        assert "1." in text
        assert "Студия Sunny Beach" in text
        assert "80,000" in text
        assert "Солнечный берег" in text


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Текст [1, 2] продолжение", "Текст продолжение"),
        ("Цена 95 000€ [12]", "Цена 95 000€"),
    ],
)
def test_multi_and_wide_citations_stripped(answer: str, expected: str) -> None:
    assert _sanitize_response_text(answer, sources_enabled=False) == expected
