"""Pytest configuration for chaos tests."""

from pathlib import Path

import pytest


_THIS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply 'chaos' marker to all tests in this directory."""
    for item in items:
        if item.path.parent == _THIS_DIR or _THIS_DIR in item.path.parents:
            item.add_marker(pytest.mark.chaos)


@pytest.fixture
def sample_context_chunks():
    """Sample context chunks for testing."""
    return [
        {
            "text": "Beautiful apartment near the beach in Sunny Beach",
            "metadata": {
                "title": "Sea View Apartment",
                "city": "Sunny Beach",
                "price": 55000,
                "rooms": 2,
            },
            "score": 0.95,
        },
        {
            "text": "Cozy studio in the heart of Burgas",
            "metadata": {
                "title": "Central Studio",
                "city": "Burgas",
                "price": 35000,
                "rooms": 1,
            },
            "score": 0.88,
        },
        {
            "text": "Spacious house with garden",
            "metadata": {
                "title": "Garden House",
                "city": "Nesebar",
                "price": 95000,
                "rooms": 4,
            },
            "score": 0.82,
        },
    ]


@pytest.fixture
def empty_context_chunks():
    """Empty context for testing fallback scenarios."""
    return []
