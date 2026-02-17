# tests/load/conftest.py
"""Load test fixtures - support live/mock toggle."""

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


_THIS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply 'load' marker to all tests in this directory."""
    for item in items:
        if item.path.parent == _THIS_DIR or _THIS_DIR in item.path.parents:
            item.add_marker(pytest.mark.load)


def use_mocks() -> bool:
    """Check if mocks should be used."""
    return os.getenv("LOAD_USE_MOCKS", "0") == "1"


@pytest.fixture
def load_config():
    """Load test configuration from env."""
    return {
        "chat_count": int(os.getenv("LOAD_CHAT_COUNT", "30")),
        "duration_min": int(os.getenv("LOAD_DURATION_MIN", "10")),
        "use_mocks": use_mocks(),
        "eviction_test_mb": int(os.getenv("EVICTION_TEST_MB", "10")),  # Configurable
    }


@pytest.fixture
def mock_voyage_service():
    """Mock VoyageService for CI."""
    service = AsyncMock()
    service.embed_query = AsyncMock(return_value=[0.1] * 1024)
    service.rerank = AsyncMock(
        return_value=[
            {"index": 0, "score": 0.95},
            {"index": 1, "score": 0.85},
        ]
    )
    return service


@pytest.fixture
def mock_qdrant_service():
    """Mock QdrantService for CI."""
    service = AsyncMock()
    service.hybrid_search_rrf = AsyncMock(
        return_value=[
            {"id": "1", "score": 0.9, "text": "Mock result 1", "metadata": {}},
            {"id": "2", "score": 0.8, "text": "Mock result 2", "metadata": {}},
        ]
    )
    return service
