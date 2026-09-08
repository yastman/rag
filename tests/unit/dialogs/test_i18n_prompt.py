"""Tests for system prompt i18n and locale plumbing (#444)."""

from __future__ import annotations

from ._property_bot_ast import get_default_map, get_parameter_names, get_property_bot_method


def test_supervisor_aligns_with_canonical_locale_codes():
    """The supervisor forwards canonical locale codes to the core (#3491).

    The legacy display-label map (``LOCALE_TO_LANGUAGE``) is gone: the core
    consumes transport-neutral codes owned by ``src.core.contracts``.
    """
    import telegram_bot.pipeline.supervisor as supervisor
    from src.core.contracts import normalize_request_language

    assert not hasattr(supervisor, "LOCALE_TO_LANGUAGE")
    assert {"ru", "en", "uk"} <= supervisor.SUPPORTED_REQUEST_LANGUAGES
    assert normalize_request_language("ru") == "ru"
    assert normalize_request_language("en") == "en"
    assert normalize_request_language("uk") == "uk"
    # Missing/unsupported locales fall back to the one canonical default.
    assert normalize_request_language("de") == "ru"
    assert normalize_request_language("") == "ru"
    assert normalize_request_language(None) == "ru"


def test_handle_query_accepts_locale_parameter():
    """handle_query signature accepts locale kwarg injected by i18n middleware."""
    method = get_property_bot_method("handle_query")
    assert "locale" in get_parameter_names(method)
    assert get_default_map(method)["locale"] == "ru"


def test_handle_query_supervisor_accepts_locale_parameter():
    """_handle_query_supervisor accepts locale kwarg."""
    method = get_property_bot_method("_handle_query_supervisor")
    assert "locale" in get_parameter_names(method)
    assert get_default_map(method)["locale"] == "ru"
