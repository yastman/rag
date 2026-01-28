"""Conftest for retrieval tests."""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_cross_encoder():
    """Provide access to mocked CrossEncoder for assertions."""
    # Get the mock from sys.modules (set up in tests/conftest.py)
    mock_st = sys.modules.get("sentence_transformers")
    if mock_st is None or not isinstance(mock_st, MagicMock):
        # Create mock if not already set
        mock_st = MagicMock()
        sys.modules["sentence_transformers"] = mock_st

    mock_encoder_instance = MagicMock()
    mock_st.CrossEncoder.return_value = mock_encoder_instance

    return {
        "encoder": mock_encoder_instance,
        "class": mock_st.CrossEncoder,
        "module": mock_st,
    }


@pytest.fixture(autouse=True)
def reset_reranker_singleton(mock_cross_encoder):
    """Reset reranker singleton before each test."""
    from src.retrieval import reranker

    reranker._cross_encoder = None

    # Reset mock call counts
    mock_cross_encoder["class"].reset_mock()
    mock_cross_encoder["encoder"].reset_mock()

    yield

    # Cleanup
    reranker._cross_encoder = None
