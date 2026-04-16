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


def test_build_filter_signature_sorts_keys_and_nested_ranges() -> None:
    signature = build_filter_signature({"price": {"lte": 80000}, "city": "Несебр"})
    assert signature == "city=Несебр|price.lte=80000"


def test_build_filter_signature_ignores_empty_filters() -> None:
    assert build_filter_signature({}) is None
