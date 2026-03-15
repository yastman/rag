"""Public API surface checks for telegram_bot.services."""


def test_llmservice_not_in_recommended_public_api():
    """LLMService remains compatibility-only and is excluded from __all__."""
    import telegram_bot.services as services

    assert "LLMService" not in services.__all__
    # Compatibility import path still available for legacy consumers.
    assert services.LLMService is not None
