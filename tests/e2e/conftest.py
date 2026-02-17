# tests/e2e/conftest.py
"""E2E test configuration."""

from pathlib import Path

import pytest


_THIS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply 'e2e' marker to all tests in this directory."""
    for item in items:
        if item.path.parent == _THIS_DIR or _THIS_DIR in item.path.parents:
            item.add_marker(pytest.mark.e2e)
