# tests/test_retriever_service.py
"""Tests for RetrieverService."""

from unittest.mock import patch


class TestRetrieverServiceFilters:
    """Test filter building logic."""

    def test_build_filter_returns_none_for_empty_dict(self):
        """Empty filters should return None, not empty Filter."""
        from telegram_bot.services import RetrieverService

        with patch.object(RetrieverService, "__init__", lambda _s, *_a, **_kw: None):
            retriever = RetrieverService.__new__(RetrieverService)
            retriever.url = "http://localhost:6333"
            retriever.api_key = ""
            retriever.collection_name = "test"
            retriever.client = None
            retriever._is_healthy = False

            result = retriever._build_filter({})

            assert result is None, "Empty filters should return None"

    def test_build_filter_returns_filter_for_city(self):
        """Filter with city should return proper Filter object."""
        from qdrant_client import models

        from telegram_bot.services import RetrieverService

        with patch.object(RetrieverService, "__init__", lambda _s, *_a, **_kw: None):
            retriever = RetrieverService.__new__(RetrieverService)

            result = retriever._build_filter({"city": "Несебр"})

            assert result is not None
            assert isinstance(result, models.Filter)
            assert len(result.must) == 1

    def test_build_base_filter_returns_none(self):
        """Base filter should return None (search all documents)."""
        from telegram_bot.services import RetrieverService

        with patch.object(RetrieverService, "__init__", lambda _s, *_a, **_kw: None):
            retriever = RetrieverService.__new__(RetrieverService)

            result = retriever._build_base_filter()

            assert result is None
