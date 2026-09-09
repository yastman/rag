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


def test_price_evidence_passes_threshold_shorthand_with_currency() -> None:
    """Threshold shorthand with explicit currency (80к евро for 80000) passes price_max."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Квартира за 80к евро в хорошем районе.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is True


def test_price_evidence_fails_bare_k_shorthand_without_currency() -> None:
    """A bare '80к' without a currency marker is ambiguous and must NOT satisfy price_max.

    Issue #3391: unsupported ambiguity is explicit and cannot count green.
    """
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Квартира за 80к в хорошем районе.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False


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


# ── issue #3391: value comparisons instead of token presence ────────────


def _rooms_scenario(rooms: int) -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="4.x",
        name="Rooms only",
        query="двухкомнатная квартира",
        group=scenarios.TestGroup.ROOM_FILTERS,
        expected_filters=scenarios.ExpectedFilters(rooms=rooms),
    )


def _price_range_scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="3.x",
        name="Price range only",
        query="от 100к до 150к",
        group=scenarios.TestGroup.PRICE_FILTERS,
        expected_filters=scenarios.ExpectedFilters(price_min=100000, price_max=150000),
    )


def _distance_scenario(distance_to_sea_max: int) -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="5.x",
        name="Distance only",
        query="до 300м от моря",
        group=scenarios.TestGroup.LOCATION_FILTERS,
        expected_filters=scenarios.ExpectedFilters(distance_to_sea_max=distance_to_sea_max),
    )


def test_price_max_rejects_higher_price_with_currency() -> None:
    """False green #1: price_max=80000 must reject a response offering 90 000 евро."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_filter_scenario(),
            "Предлагаем квартиру за 90 000 евро в центре.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is False
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["price_max"]["expected"] == "all prices <= 80000"
    assert diagnostics["price_max"]["observed"] == [90000]


def test_price_min_rejects_price_below_min() -> None:
    """price_min=100000 must reject a response offering 80 000 евро."""
    judge = PassthroughJudge(E2EConfig())
    scenario = scenarios.TestScenario(
        id="3.y",
        name="Price min only",
        query="квартиры от 100к евро",
        group=scenarios.TestGroup.PRICE_FILTERS,
        expected_filters=scenarios.ExpectedFilters(price_min=100000),
    )
    result = asyncio.run(judge.evaluate(scenario, "Вариант за 80 000 евро."))

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_min"] is False
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["price_min"]["expected"] == "all prices >= 100000"
    assert diagnostics["price_min"]["observed"] == [80000]


def test_price_range_accepts_in_range_response() -> None:
    """Both bounds hold when every explicit price is inside the requested range."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _price_range_scenario(),
            "Квартиры от 100 000 до 150 000 евро в Несебре.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_min"] is True
    assert evidence["price_max"] is True


def test_price_max_accepts_exact_boundary_value() -> None:
    """A price exactly equal to price_max satisfies the upper bound."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(_price_filter_scenario(), "Квартира за 80 000 евро у моря.")
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["price_max"] is True


def test_rooms_rejects_response_with_only_unrelated_price_digits() -> None:
    """False green #2: rooms=2 must reject a response that only mentions '120000 евро'."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_rooms_scenario(rooms=2), "Квартира за 120000 евро."))

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["rooms"] is False
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["rooms"]["expected"] == "room count == 2"
    assert diagnostics["rooms"]["observed"] == []


def test_rooms_rejects_different_room_count() -> None:
    """rooms=2 must reject a response offering a 3-room apartment."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _rooms_scenario(rooms=2),
            "Трехкомнатные квартиры за 120000 евро с видом на море.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["rooms"] is False
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["rooms"]["observed"] == [3]


def test_rooms_accepts_exact_value_with_room_context() -> None:
    """rooms=2 accepts a response that names the requested room count."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _rooms_scenario(rooms=2),
            "Двухкомнатные квартиры с видом на море.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["rooms"] is True


def test_distance_rejects_generic_text_without_distance_value() -> None:
    """False green #3: distance bound must reject generic text with no distance value."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _distance_scenario(distance_to_sea_max=300),
            "Предлагаем вам лучшие квартиры в Болгарии у моря.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["distance_to_sea_max"] is False
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["distance_to_sea_max"]["expected"] == "all distances <= 300 м"
    assert diagnostics["distance_to_sea_max"]["observed"] == []


def test_distance_rejects_distance_above_bound() -> None:
    """distance_to_sea_max=300 must reject a response naming 800 м."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _distance_scenario(distance_to_sea_max=300),
            "Квартира в 800 м от моря.",
        )
    )

    assert result.passed is False
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["distance_to_sea_max"] is False
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["distance_to_sea_max"]["observed"] == [800]


def test_distance_accepts_value_within_bound() -> None:
    """distance_to_sea_max=300 accepts a response naming 250 метров."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _distance_scenario(distance_to_sea_max=300),
            "Квартиры в 250 метрах от моря.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    evidence = result.check_details["filter_evidence"]
    assert evidence is not None
    assert evidence["distance_to_sea_max"] is True


def test_area_m2_is_not_counted_as_distance() -> None:
    """Apartment area (м²) must not be parsed as a distance to the sea."""
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(
        judge.evaluate(
            _distance_scenario(distance_to_sea_max=300),
            "Квартира площадью 90 м² в 200 м от пляжа.",
        )
    )

    assert result.passed is True
    assert result.check_details is not None
    diagnostics = result.check_details["filter_diagnostics"]
    assert diagnostics["distance_to_sea_max"]["observed"] == [200]


def test_numeric_keyword_not_matched_inside_larger_number() -> None:
    """Numeric keyword '120' must not match inside '1200' (digit-substring false green)."""
    judge = PassthroughJudge(E2EConfig())
    scenario = scenarios.TestScenario(
        id="8.x",
        name="Numeric keyword",
        query="найди квартиру у моря до 120 тысяч",
        group=scenarios.TestGroup.SEARCH,
        expected_keywords=["120"],
    )
    result = asyncio.run(judge.evaluate(scenario, "Квартиры от 1200 евро у моря."))

    assert result.passed is False
    assert result.check_details is not None
    assert result.check_details["expected_keywords"] is False


def test_numeric_keyword_matches_standalone_number() -> None:
    """Numeric keyword '120' matches as a standalone number ('120 тысяч')."""
    judge = PassthroughJudge(E2EConfig())
    scenario = scenarios.TestScenario(
        id="8.x",
        name="Numeric keyword",
        query="найди квартиру у моря до 120 тысяч",
        group=scenarios.TestGroup.SEARCH,
        expected_keywords=["120"],
    )
    result = asyncio.run(judge.evaluate(scenario, "Бюджет до 120 тысяч евро — есть варианты."))

    assert result.passed is True
    assert result.check_details is not None
    assert result.check_details["expected_keywords"] is True


# ── issue #3391: no-judge scenario set over the real fixtures ────────────


def _canonical_response(filters: scenarios.ExpectedFilters) -> str:
    """Build a correct response that states the exact requested values."""
    parts: list[str] = []
    if filters.price_min is not None and filters.price_max is not None:
        parts.append(f"Квартиры от {filters.price_min} до {filters.price_max} евро.")
    elif filters.price_max is not None:
        parts.append(f"Квартиры до {filters.price_max} евро.")
    elif filters.price_min is not None:
        parts.append(f"Квартиры от {filters.price_min} евро.")
    if filters.rooms is not None:
        if filters.rooms == 0:
            parts.append("Студия с балконом.")
        else:
            room_words = {1: "одно", 2: "двух", 3: "трех", 4: "четырех", 5: "пяти", 6: "шести"}
            parts.append(f"{room_words[filters.rooms]}комнатные квартиры.")
    if filters.city is not None:
        parts.append(f"Объекты в районе {filters.city}.")
    if filters.distance_to_sea_max is not None:
        parts.append(f"До моря {filters.distance_to_sea_max} м.")
    return " ".join(parts)


def test_no_judge_scenario_set_passes_with_exact_values() -> None:
    """Every filter scenario passes when the response states the exact requested values."""
    judge = PassthroughJudge(E2EConfig())
    filter_scenarios = [s for s in scenarios.SCENARIOS if s.expected_filters is not None]
    assert filter_scenarios, "expected filter scenarios in SCENARIOS"

    for scenario in filter_scenarios:
        assert scenario.expected_filters is not None
        result = asyncio.run(
            judge.evaluate(scenario, _canonical_response(scenario.expected_filters))
        )
        assert result.passed is True, f"{scenario.id}: {result.summary}"
