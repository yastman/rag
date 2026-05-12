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
