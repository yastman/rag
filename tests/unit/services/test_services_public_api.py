"""Public API surface checks for telegram_bot.services."""

import pytest


def test_llmservice_is_no_longer_exported():
    """LLMService was removed in #1541 (residual): neither __all__ nor lazy map."""
    import telegram_bot.services as services

    assert "LLMService" not in services.__all__
    with pytest.raises(AttributeError):
        services.LLMService  # noqa: B018  — accessing must now fail loudly


def test_low_confidence_threshold_is_no_longer_exported():
    """LOW_CONFIDENCE_THRESHOLD was removed in #1541 (residual)."""
    import telegram_bot.services as services

    assert "LOW_CONFIDENCE_THRESHOLD" not in services.__all__
    with pytest.raises(AttributeError):
        services.LOW_CONFIDENCE_THRESHOLD  # noqa: B018


def test_confidence_result_is_no_longer_exported():
    """ConfidenceResult was removed in #1541 (residual)."""
    import telegram_bot.services as services

    assert "ConfidenceResult" not in services.__all__
    with pytest.raises(AttributeError):
        services.ConfidenceResult  # noqa: B018
