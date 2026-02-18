# tests/test_retriever_service.py
"""Tests for RetrieverService."""

import pytest

from telegram_bot.services.retriever import RetrieverService


@pytest.fixture
def retriever() -> RetrieverService:
    """Create RetrieverService instance without running network-bound __init__."""
    instance = RetrieverService.__new__(RetrieverService)
    instance.url = "http://localhost:6333"
    instance.api_key = ""
    instance.collection_name = "test"
    instance.client = None
    instance._is_healthy = False
    return instance


class TestRetrieverServiceFilters:
    """Test filter building logic."""

    def test_build_filter_returns_none_for_empty_dict(self, retriever):
        """Empty filters should return None, not empty Filter."""
        result = retriever._build_filter({})

        assert result is None, "Empty filters should return None"

    def test_build_filter_returns_filter_for_city(self, retriever):
        """Filter with city should return proper Filter object."""
        from qdrant_client import models

        result = retriever._build_filter({"city": "Несебр"})

        assert result is not None
        assert isinstance(result, models.Filter)
        assert len(result.must) == 1

    def test_build_base_filter_returns_none(self, retriever):
        """Base filter should return None (search all documents)."""
        result = retriever._build_base_filter()

        assert result is None
