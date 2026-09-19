"""Unit tests for no-judge passthrough mode."""

from __future__ import annotations

import asyncio

from scripts.e2e import scenarios as scenarios
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


def _price_range_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="3.5",
        name="Price range",
        query="квартиры от 60000 до 80000 евро",
        group=scenarios.TestGroup.PRICE_FILTERS,
        expected_filters=scenarios.ExpectedFilters(price_min=60000, price_max=80000),
    )


def _rooms_filter_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="4.2",
        name="Two rooms",
        query="двухкомнатная квартира",
        group=scenarios.TestGroup.ROOM_FILTERS,
        expected_filters=scenarios.ExpectedFilters(rooms=2),
    )


def _distance_filter_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="5.3",
        name="Distance to sea",
        query="квартира до 500 метров от моря",
        group=scenarios.TestGroup.LOCATION_FILTERS,
        expected_filters=scenarios.ExpectedFilters(distance_to_sea_max=500),
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


def test_price_evidence_fails_digits_before_longer_euro_word() -> None:
    """Numeric text followed by longer word beginning with евро must NOT satisfy price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Есть 70000 европейских вариантов.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False


def test_passthrough_judge_rejects_price_above_requested_maximum() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_price_filter_scenario(), "Подходит квартира за 90 000 евро.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"price_max": False}
    assert result.check_details["filter_diagnostics"] == {
        "price_max": "expected <= 80000 EUR; observed EUR values: 90000"
    }


def test_passthrough_judge_rejects_price_digits_as_room_evidence() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_rooms_filter_scenario(), "Есть вариант за 120 000 евро."))

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"rooms": False}
    assert result.check_details["filter_diagnostics"] == {
        "rooms": "expected 2 rooms; observed room counts: none"
    }


def test_passthrough_judge_rejects_sea_mention_without_bounded_distance() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира рядом с морем и пляжем.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"distance_to_sea_max": False}
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: none"
    }


def test_passthrough_judge_accepts_distance_within_requested_maximum() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира находится в 450 м от моря.")
    )

    assert result.passed is True
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"distance_to_sea_max": True}
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 450"
    }


def test_passthrough_judge_normalizes_complete_decimal_k_price_tokens() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_price_filter_scenario(), "Цена квартиры 90.5k евро."))

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "price_max": "expected <= 80000 EUR; observed EUR values: 90500"
    }


def test_passthrough_judge_rejects_unsupported_dotted_price_without_suffix_match() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_price_filter_scenario(), "Цена квартиры 90.000 евро."))

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "price_max": (
            "expected <= 80000 EUR; observed EUR values: none; unsupported EUR tokens: 90.000"
        )
    }


def test_passthrough_judge_rejects_conflicting_price_range_values() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_range_scenario(),
            "Цены квартир 50 000 евро и 100 000 евро.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"price_max": False, "price_min": False}
    assert result.check_details["filter_diagnostics"] == {
        "price_max": "expected <= 80000 EUR; observed EUR values: 50000, 100000",
        "price_min": "expected >= 60000 EUR; observed EUR values: 50000, 100000",
    }


def test_passthrough_judge_rejects_mixed_prices_for_upper_bound() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_price_filter_scenario(), "Есть варианты за 70 000 евро и 90 000 евро.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"price_max": False}


def test_passthrough_judge_rejects_decimal_room_token() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_rooms_filter_scenario(), "Есть 2.2-комнатная квартира."))

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "rooms": ("expected 2 rooms; observed room counts: none; unsupported room tokens: 2.2")
    }


def test_passthrough_judge_rejects_mixed_room_counts() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _rooms_filter_scenario(),
            "Есть 2-комнатная квартира и 3-комнатная квартира.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"rooms": False}
    assert result.check_details["filter_diagnostics"] == {
        "rooms": "expected 2 rooms; observed room counts: 2, 3"
    }


def test_passthrough_judge_rejects_non_sea_distance_and_distant_sea() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _distance_filter_scenario(),
            "До магазина 100 м, до моря 2 км.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"distance_to_sea_max": False}
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 2000"
    }


def test_passthrough_judge_rejects_distance_just_above_meter_bound() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира расположена в 500.4 м от моря.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 500.4"
    }


def test_passthrough_judge_rejects_distance_just_above_kilometer_bound() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира расположена в 0.5004 км от моря.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 500.4"
    }


def test_passthrough_judge_accepts_distance_at_kilometer_bound() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира расположена в 0.5 км от моря.")
    )

    assert result.passed is True
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 500"
    }


def test_passthrough_judge_normalizes_nonbreaking_space_price_grouping() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_price_filter_scenario(), "Цена квартиры 90\u00a0000 евро.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "price_max": "expected <= 80000 EUR; observed EUR values: 90000"
    }


def test_passthrough_judge_normalizes_narrow_nonbreaking_space_price_grouping() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_price_filter_scenario(), "Цена квартиры 90\u202f000 евро.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "price_max": "expected <= 80000 EUR; observed EUR values: 90000"
    }


def test_passthrough_judge_rejects_valid_price_with_unsupported_price_token() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Есть варианты за 70 000 евро и 90.000 евро.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"price_max": False}
    assert result.check_details["filter_diagnostics"] == {
        "price_max": (
            "expected <= 80000 EUR; observed EUR values: 70000; unsupported EUR tokens: 90.000"
        )
    }


def test_passthrough_judge_rejects_valid_room_with_unsupported_room_token() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _rooms_filter_scenario(),
            "Есть 2-комнатная квартира и 2.2-комнатная квартира.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"rooms": False}
    assert result.check_details["filter_diagnostics"] == {
        "rooms": ("expected 2 rooms; observed room counts: 2; unsupported room tokens: 2.2")
    }


def test_passthrough_judge_normalizes_grouped_sea_distance() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира находится в 1 000 м от моря.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 1000"
    }


def test_passthrough_judge_normalizes_nonbreaking_space_grouped_sea_distance() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_distance_filter_scenario(), "Квартира находится в 1\u00a0000 м от моря.")
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": "expected <= 500 m; observed distances: 1000"
    }


def test_passthrough_judge_rejects_valid_distance_with_unsupported_distance_token() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _distance_filter_scenario(),
            "Квартира находится в 100 м от моря и 1.000.000 м от моря.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["filter_evidence"] == {"distance_to_sea_max": False}
    assert result.check_details["filter_diagnostics"] == {
        "distance_to_sea_max": (
            "expected <= 500 m; observed distances: 100; unsupported distance tokens: 1.000.000"
        )
    }
