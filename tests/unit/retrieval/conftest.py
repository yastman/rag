"""Conftest for retrieval tests."""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_cross_encoder(monkeypatch):
    """Provide access to mocked CrossEncoder for assertions.

    Since reranker.py now uses lazy import, we need to ensure the mock
    is in sys.modules BEFORE the test imports reranker.

    Uses monkeypatch.setitem for automatic teardown of sys.modules entries.

    Returns dict with:
    - encoder: Mock CrossEncoder instance
    - class: Mock CrossEncoder class
    - module: Mock sentence_transformers module
    - reranker: Fresh reranker module with mock in place
    """
    # Clear reranker from module cache FIRST
    sys.modules.pop("src.retrieval.reranker", None)

    # Create fresh mock and install BEFORE importing reranker
    mock_st = MagicMock()
    mock_encoder_instance = MagicMock()
    mock_st.CrossEncoder.return_value = mock_encoder_instance
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_st)

    # Now import reranker - it will use our mock
    from src.retrieval import reranker

    reranker._cross_encoder = None

    return {
        "encoder": mock_encoder_instance,
        "class": mock_st.CrossEncoder,
        "module": mock_st,
        "reranker": reranker,
    }


@pytest.fixture
def reranker(mock_cross_encoder):
    """Provide fresh reranker module with mock in place.

    Use this fixture in tests: `def test_foo(reranker, mock_cross_encoder):`
    """
    return mock_cross_encoder["reranker"]


@pytest.fixture(autouse=True)
def reset_reranker_singleton(mock_cross_encoder):
    """Reset reranker singleton and mock call counts before each test."""
    reranker_mod = mock_cross_encoder["reranker"]
    reranker_mod._cross_encoder = None

    # Reset mock call counts
    mock_cross_encoder["class"].reset_mock()
    mock_cross_encoder["encoder"].reset_mock()

    yield

    # Cleanup
    reranker_mod._cross_encoder = None
