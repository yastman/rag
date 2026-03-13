"""Conftest for ingestion unit tests.

Mocks heavy ML dependencies (fastembed) before test collection
so that gdrive_indexer.py can be imported without the actual package.
"""

import sys
from unittest.mock import MagicMock


_MOCKED_MODULES: list[str] = []


def pytest_configure(config: object) -> None:
    """Mock unavailable heavy ML deps before test collection."""
    if "fastembed" not in sys.modules:
        mock_fastembed = MagicMock()
        mock_fastembed.SparseTextEmbedding = MagicMock()
        sys.modules["fastembed"] = mock_fastembed
        _MOCKED_MODULES.append("fastembed")


def pytest_unconfigure(config: object) -> None:
    """Clean up mocked modules after tests."""
    for mod in _MOCKED_MODULES:
        sys.modules.pop(mod, None)
    _MOCKED_MODULES.clear()
