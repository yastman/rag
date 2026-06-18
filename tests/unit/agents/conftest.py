"""Conftest for tests/unit/agents/ — patches src.runtime.pipeline.rag.get_client
so that tests calling _hybrid_retrieve don't fail with
'NoneType' object has no attribute 'update_current_span'.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_rag_get_client():
    """Auto-patch src.runtime.pipeline.rag.get_client for all agent unit tests."""
    mock_lf = MagicMock()
    with patch("src.runtime.pipeline.rag.get_client", return_value=mock_lf):
        yield mock_lf
