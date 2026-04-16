import pytest

from telegram_bot.services.query_filter_signal import (
    QueryFilterSignal,
    build_filter_signature,
    detect_filter_sensitive_query,
)


def test_detect_filter_sensitive_query_for_city_and_price() -> None:
    signal = detect_filter_sensitive_query("студия в Несебре до 80000 евро")
    assert signal == QueryFilterSignal(
        is_filter_sensitive=True,
        reasons=("city", "price", "rooms", "currency"),
    )


def test_detect_filter_sensitive_query_for_plain_faq() -> None:
    signal = detect_filter_sensitive_query("какие документы нужны для внж")
    assert signal == QueryFilterSignal(is_filter_sensitive=False, reasons=())


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("квартира на 3 этаже", "floor"),
        ("квартира до моря 200 метров", "distance_to_sea"),
        ("апартамент с таксой поддержки 12 евро", "maintenance"),
        ("квартира с 2 санузлами", "bathrooms"),
        ("квартира с мебелью", "furniture"),
        ("квартира для круглогодичного проживания", "year_round"),
    ],
)
def test_detect_filter_sensitive_query_for_remaining_supported_filters(
    query: str, reason: str
) -> None:
    signal = detect_filter_sensitive_query(query)
    assert signal.is_filter_sensitive is True
    assert reason in signal.reasons


def test_build_filter_signature_sorts_keys_and_nested_ranges() -> None:
    signature = build_filter_signature({"price": {"lte": 80000}, "city": "Несебр"})
    assert signature == "city=Несебр|price.lte=80000"


def test_build_filter_signature_ignores_empty_filters() -> None:
    assert build_filter_signature({}) is None
