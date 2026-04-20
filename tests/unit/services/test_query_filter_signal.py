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


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("апартамент на первой линии", "distance_to_sea"),
        ("квартира у моря", "distance_to_sea"),
        ("квартира не дальше 600м от пляжа", "distance_to_sea"),
        ("апартамент в 400м от моря", "distance_to_sea"),
        ("апартамент с низкой таксой", "maintenance"),
        ("квартира на 4", "floor"),
        ("квартира с двумя санузлами", "bathrooms"),
        ("обставленная квартира", "furniture"),
        ("меблированная квартира", "furniture"),
        ("апартамент для жизни круглый год", "year_round"),
        ("зимой можно жить", "year_round"),
    ],
)
def test_detect_filter_sensitive_query_for_extractor_supported_forms(
    query: str, reason: str
) -> None:
    signal = detect_filter_sensitive_query(query)
    assert signal.is_filter_sensitive is True
    assert reason in signal.reasons


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("квартира в Софии", "city"),
        ("апартамент в Свети Власе", "city"),
        ("двухкомнатная квартира в Созополе", "rooms"),
        ("трехкомнатная квартира у моря", "rooms"),
        ("однокомнатная квартира в Несебре", "rooms"),
    ],
)
def test_detect_filter_sensitive_query_for_supported_apartment_city_and_room_forms(
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
