"""Tests for custom vectorizers.

UserBaseVectorizer (deepvk/USER2-base) was removed — see src/services/vectorizers.py.
Tests for the active BgeM3CacheVectorizer live in tests/unit/services/.
"""


def test_vectorizers_module_importable() -> None:
    """Active vectorizer module imports without error."""
    from telegram_bot.services.rag.vectorizers import BgeM3CacheVectorizer

    assert BgeM3CacheVectorizer is not None
