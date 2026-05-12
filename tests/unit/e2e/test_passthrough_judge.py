"""Unit tests for no-judge passthrough mode."""

from __future__ import annotations

import asyncio

from scripts.e2e import test_scenarios as scenarios
from scripts.e2e.claude_judge import PassthroughJudge
from scripts.e2e.config import E2EConfig


def _chitchat_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="2.4",
        name="How are you",
        query="Как дела?",
        group=scenarios.TestGroup.CHITCHAT,
        should_skip_rag=True,
    )


def _immigration_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="0.1",
        name="Digital Nomad visa basics",
        query="Какие требования для визы Digital Nomad в Болгарии?",
        group=scenarios.TestGroup.IMMIGRATION,
        expected_keywords=["digital", "nomad", "виза", "болгар"],
    )


def _search_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="6.3",
        name="Complex query",
        query="2-комн в Солнечный берег до 120к с видом на море",
        group=scenarios.TestGroup.SEARCH,
        expected_filters=scenarios.ExpectedFilters(
            rooms=2, city="Солнечный берег", price_max=120000
        ),
        expected_keywords=["Солнечн", "мор"],
    )


def _price_filter_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="3.1",
        name="Price max",
        query="квартиры до 80000 евро",
        group=scenarios.TestGroup.PRICE_FILTERS,
        expected_filters=scenarios.ExpectedFilters(price_max=80000),
    )


def test_passthrough_judge_chitchat_passes_with_response_presence() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_chitchat_scenario(), "Привет! Как дела?"))

    assert result.passed is True
    assert result.check_details is not None
    assert result.check_details["presence"] is True
    assert result.check_details["expected_keywords"] is None


def test_passthrough_judge_fails_empty_response() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_chitchat_scenario(), ""))

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["presence"] is False


def test_passthrough_judge_passes_with_expected_keywords() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _immigration_scenario(),
            "Для визы Digital Nomad в Болгарии нужны документы.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    assert result.check_details["expected_keywords"] is True


def test_passthrough_judge_fails_missing_expected_keywords() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _immigration_scenario(),
            "Я не знаю, что сказать.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["expected_keywords"] is False


def test_passthrough_judge_fails_generic_fallback_for_rag() -> None:
    judge = PassthroughJudge(E2EConfig())
    scenario = scenarios.TestScenario(
        id="3.1",
        name="Price max",
        query="квартиры до 80000 евро",
        group=scenarios.TestGroup.PRICE_FILTERS,
        expected_filters=scenarios.ExpectedFilters(price_max=80000),
    )
    result = asyncio.run(
        judge.evaluate(
            scenario,
            "К сожалению, не удалось найти подходящую информацию. "
            "Попробуйте переформулировать запрос.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["generic_fallback"] is True


def test_passthrough_judge_passes_without_fallback_for_rag() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_price_filter_scenario(), "Нашел квартиру за 70 000 евро."))

    assert result.passed is True
    assert result.check_details is not None
    assert result.check_details["generic_fallback"] is False


def test_passthrough_judge_fails_missing_filter_evidence() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_search_scenario(), "Есть хорошие варианты."))

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["rooms"] is False
    assert evidence["city"] is False
    assert evidence["price_max"] is False


def test_passthrough_judge_passes_with_filter_evidence() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _search_scenario(),
            "2-комнатная в Солнечном береге за 120 000 евро с видом на море.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["rooms"] is True
    assert evidence["city"] is True
    assert evidence["price_max"] is True


# ── price filter evidence: currency-only rejection ──────────────────────


def test_price_evidence_fails_currency_only_text() -> None:
    """Currency-only text like 'Все цены указаны в евро' must NOT satisfy price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Все цены указаны в евро.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False


def test_price_evidence_fails_euro_sign_only() -> None:
    """Standalone € without a numeric price token must NOT satisfy price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Стоимость указана в €.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False


def test_price_evidence_passes_numeric_price_with_currency() -> None:
    """Numeric price token together with currency passes price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Нашел квартиру за 70 000 евро с двумя спальнями.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is True


def test_price_evidence_passes_numeric_price_with_euro_sign() -> None:
    """Numeric price token with € passes price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Есть вариант за 65000€ в центре.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is True


def test_price_evidence_passes_threshold_shorthand() -> None:
    """Exact threshold shorthand (80к for 80000) passes without currency."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Квартира за 80к в хорошем районе.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is True


def test_price_evidence_fails_no_price_or_currency() -> None:
    """Text with no price number and no currency must fail price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Есть хорошие варианты недвижимости.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False


def test_price_evidence_euro_in_euro_word_alone_fails() -> None:
    """The substring 'евро' inside another word without a number must fail."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Обсуждаем европейскую недвижимость.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False
