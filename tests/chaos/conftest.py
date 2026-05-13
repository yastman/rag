"""Pytest configuration for chaos tests."""

import pytest


@pytest.fixture
def empty_context_chunks():
    """Empty context for testing fallback scenarios."""
    return []
