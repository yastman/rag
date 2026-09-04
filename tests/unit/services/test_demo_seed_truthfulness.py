"""Demo seed ↔ visible prompts truthfulness contract (#3203).

Locks together, through the production extraction path:
- the shipped synthetic seed (data/apartments.csv),
- the golden demo queries shown on the demo keyboard,
- the intentional no-result query,
- the canonical demo domain shared by UI options and the HardFilters schema.

The in-memory ``_matches`` evaluator mirrors the Qdrant filter semantics of
``_build_apartment_filter`` (MatchValue / Range / MatchAny); the live end-to-end
equivalent is covered by integration tests against a real collection.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from src.models.apartment import ApartmentRecord
from src.runtime.domain_defaults import (
    DEMO_CITIES,
    DEMO_COMPLEX_CITIES,
    GOLDEN_DEMO_QUERIES,
    GOLDEN_QUERY_MIN_RESULTS,
    NO_RESULT_DEMO_QUERY,
)
from telegram_bot.constants.apartment_constants import APARTMENT_CITY_OPTIONS
from telegram_bot.services.apartment.apartment_filter_extractor import (
    ApartmentFilterExtractor,
)
from telegram_bot.services.apartment.apartments_service import generate_search_examples


REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_PATH = REPO_ROOT / "data" / "apartments.csv"

_extractor = ApartmentFilterExtractor()


@pytest.fixture(scope="module")
def seed() -> list[dict[str, Any]]:
    return _load_seed()


# ---------------------------------------------------------------------------
# Fixtures: seed rows + production filters
# ---------------------------------------------------------------------------


def _load_seed() -> list[dict[str, Any]]:
    with open(SEED_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [ApartmentRecord.from_raw(row).to_payload() for row in reader]


def _extract_filters(query: str) -> dict[str, Any]:
    """Production regex extraction → Qdrant-compatible filters dict."""
    return _extractor.parse(query).to_filters_dict()


def _matches(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Mirror of _build_apartment_filter semantics (MatchValue/Range/MatchAny)."""
    for key, value in filters.items():
        actual = payload.get(key)
        if isinstance(value, list):
            if not isinstance(actual, list) or not set(value) & set(actual):
                return False
        elif isinstance(value, bool):
            if bool(actual) is not value:
                return False
        elif isinstance(value, dict):
            if actual is None:
                return False
            if "gte" in value and float(actual) < float(value["gte"]):
                return False
            if "lte" in value and float(actual) > float(value["lte"]):
                return False
            if "gt" in value and float(actual) <= float(value["gt"]):
                return False
            if "lt" in value and float(actual) >= float(value["lt"]):
                return False
        elif actual != value:
            return False
    return True


def _match_count(seed: list[dict[str, Any]], filters: dict[str, Any]) -> int:
    return sum(1 for payload in seed if _matches(payload, filters))


# ---------------------------------------------------------------------------
# Cross-surface reconciliation: seed domain = schema = UI = visible prompts
# ---------------------------------------------------------------------------


class TestDomainReconciliation:
    def test_hard_filters_city_literal_is_demo_cities(self) -> None:
        from typing import get_args

        from src.models.apartment import HardFilters

        annotation = HardFilters.model_fields["city"].annotation
        (literal_type, _) = get_args(annotation)
        assert get_args(literal_type) == DEMO_CITIES

    def test_hard_filters_complex_description_lists_demo_complexes(self) -> None:
        from src.models.apartment import HardFilters

        description = HardFilters.model_fields["complex_name"].description or ""
        for complex_name in DEMO_COMPLEX_CITIES:
            assert complex_name in description

    def test_filter_dialog_city_options_are_demo_cities(self) -> None:
        assert [(city, city) for city in DEMO_CITIES] == APARTMENT_CITY_OPTIONS

    def test_funnel_city_and_complex_options_are_demo_domain(self) -> None:
        from telegram_bot.dialogs.funnel import _constants

        city_values = [value for _, value in _constants._CITY_OPTIONS]
        assert city_values == [*DEMO_CITIES, "any"]

        complex_values = [value for _, value in _constants._COMPLEX_OPTIONS]
        assert complex_values == [*sorted(DEMO_COMPLEX_CITIES), "any"]

    def test_extractor_complex_aliases_cover_demo_complexes(self) -> None:
        from telegram_bot.services.apartment.apartment_filter_extractor import (
            _COMPLEX_ALIASES,
        )

        assert set(_COMPLEX_ALIASES.values()) == set(DEMO_COMPLEX_CITIES)

    def test_demo_keyboard_defaults_are_the_golden_queries(self) -> None:
        from telegram_bot.keyboards.demo_keyboard import DEFAULT_EXAMPLES

        assert list(GOLDEN_DEMO_QUERIES) == DEFAULT_EXAMPLES

    def test_seed_matches_demo_domain(self, seed: list[dict[str, Any]]) -> None:
        assert {p["city"] for p in seed} == set(DEMO_CITIES)
        assert {p["complex_name"] for p in seed} == set(DEMO_COMPLEX_CITIES)
        for payload in seed:
            assert DEMO_COMPLEX_CITIES[payload["complex_name"]] == payload["city"]


# ---------------------------------------------------------------------------
# Golden queries and the no-result query through the production filter path
# ---------------------------------------------------------------------------


class TestGoldenQueriesReturnResults:
    def test_every_golden_query_extracts_filters(self) -> None:
        for query in GOLDEN_DEMO_QUERIES:
            filters = _extract_filters(query)
            assert filters, f"Golden query extracts no filters: {query}"

    def test_every_golden_query_returns_minimum_results(self, seed: list[dict[str, Any]]) -> None:
        for query in GOLDEN_DEMO_QUERIES:
            count = _match_count(seed, _extract_filters(query))
            assert count >= GOLDEN_QUERY_MIN_RESULTS, f"{query}: only {count} matches"

    def test_no_result_query_is_empty_by_design(self, seed: list[dict[str, Any]]) -> None:
        filters = _extract_filters(NO_RESULT_DEMO_QUERY)
        assert filters, "No-result query must exercise real filters, not absence of them"
        assert _match_count(seed, filters) == 0


# ---------------------------------------------------------------------------
# Seed hygiene: deterministic synthetic fixture, no PII
# ---------------------------------------------------------------------------


class TestSeedHygiene:
    def test_seed_is_large_enough_for_the_integration_contract(
        self, seed: list[dict[str, Any]]
    ) -> None:
        # tests/integration/test_apartments_ingestion.py requires >= 297 points.
        assert len(seed) >= 297

    def test_seed_identities_are_unique(self, seed: list[dict[str, Any]]) -> None:
        identities = [(p["complex_name"], p["section"], p["apartment_number"]) for p in seed]
        assert len(identities) == len(set(identities))

    def test_seed_rooms_cover_filter_dialog_options(self, seed: list[dict[str, Any]]) -> None:
        rooms = {p["rooms"] for p in seed}
        assert rooms == {1, 2, 3, 4, 5}

    def test_seed_views_cover_filter_dialog_options(self, seed: list[dict[str, Any]]) -> None:
        from telegram_bot.dialogs.filter_constants import VIEW_DISPLAY

        primaries = {p["view_primary"] for p in seed}
        assert set(VIEW_DISPLAY) <= primaries

    def test_seed_has_furnished_and_promotion_rows(self, seed: list[dict[str, Any]]) -> None:
        assert any(p["is_furnished"] for p in seed)
        assert any(not p["is_furnished"] for p in seed)
        assert any(p["is_promotion"] for p in seed)

    def test_seed_contains_no_pii(self, seed: list[dict[str, Any]]) -> None:
        """Synthetic fixture: no emails, no phone-number prefixes, only known fields."""
        blob = "\n".join(str(v) for payload in seed for v in payload.values()).lower()
        assert "@" not in blob, "Seed must not contain emails"
        for prefix in ("+7", "+359", "+49", "+380"):
            assert prefix not in blob, f"Seed must not contain phone prefixes ({prefix})"

    def test_seed_is_deterministic(self) -> None:
        """The tracked CSV must be byte-identical to the generator output."""
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "apartments" / "generate_seed.py"),
                "--check",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Dynamic example generation advertises only existing combinations
# ---------------------------------------------------------------------------


def _stats_from_seed(seed: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the get_collection_stats shape from seed payloads."""
    cities = sorted({p["city"] for p in seed})
    complexes = sorted({p["complex_name"] for p in seed})
    city_combos: dict[str, dict[int, dict]] = {}
    complex_combos: dict[str, dict[int, int]] = {}
    city_prices: dict[str, list[float]] = {}
    prices: list[float] = []
    rooms_set: set[int] = set()
    for p in seed:
        rooms = int(p["rooms"])
        price = float(p["price_eur"])
        rooms_set.add(rooms)
        prices.append(price)
        city_prices.setdefault(p["city"], []).append(price)
        entry = city_combos.setdefault(p["city"], {}).setdefault(
            rooms, {"count": 0, "max_price": 0.0}
        )
        entry["count"] += 1
        entry["max_price"] = max(entry["max_price"], price)
        complex_combos.setdefault(p["complex_name"], {})
        rooms_map = complex_combos[p["complex_name"]]
        rooms_map[rooms] = rooms_map.get(rooms, 0) + 1
    return {
        "cities": cities,
        "complexes": complexes,
        "rooms": sorted(rooms_set),
        "min_price": min(prices),
        "max_price": max(prices),
        "city_combos": {
            c: [{"rooms": r, **v} for r, v in sorted(m.items())] for c, m in city_combos.items()
        },
        "complex_combos": {
            c: [{"rooms": r, "count": n} for r, n in sorted(m.items())]
            for c, m in complex_combos.items()
        },
        "city_prices": {c: sorted(v) for c, v in city_prices.items()},
    }


class TestDynamicExamplesAreTruthful:
    def test_every_dynamic_example_matches_seed_data(self, seed: list[dict[str, Any]]) -> None:
        examples = generate_search_examples(_stats_from_seed(seed))
        assert len(examples) == 4
        for example in examples:
            filters = _extract_filters(example)
            assert filters, f"Example extracts no filters: {example}"
            count = _match_count(seed, filters)
            assert count >= 1, f"Example promises data that does not exist: {example}"

    def test_dynamic_examples_prefer_coherent_combinations(
        self, seed: list[dict[str, Any]]
    ) -> None:
        examples = generate_search_examples(_stats_from_seed(seed))
        combo_examples = [
            e
            for e in examples
            if any(city_prompt in e for city_prompt in ("Солнечн", "Влас", "Элените")) and "€" in e
        ]
        for example in combo_examples:
            assert _match_count(seed, _extract_filters(example)) >= GOLDEN_QUERY_MIN_RESULTS

    def test_examples_are_diverse(self, seed: list[dict[str, Any]]) -> None:
        examples = generate_search_examples(_stats_from_seed(seed))
        assert len(set(examples)) == 4
