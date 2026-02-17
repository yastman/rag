# tests/benchmark/conftest.py
"""Benchmark test configuration."""

from pathlib import Path

import pytest


_THIS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply 'benchmark' marker to all tests in this directory."""
    for item in items:
        if item.path.parent == _THIS_DIR or _THIS_DIR in item.path.parents:
            item.add_marker(pytest.mark.benchmark)
