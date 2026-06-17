"""Contracts for the disabled RAGAS evaluation lane (#2043)."""

from __future__ import annotations

import pytest

from src.evaluation import ragas_evaluation


def test_ragas_evaluation_imports_without_ragas_dependency() -> None:
    """The compatibility module must not import the removed ragas package."""
    assert "ragas is not declared" in ragas_evaluation.RAGAS_UNAVAILABLE_MESSAGE


def test_ragas_evaluation_runtime_fails_with_clear_message() -> None:
    """Old callers should get an actionable error instead of ModuleNotFoundError."""
    with pytest.raises(ragas_evaluation.RAGASEvaluationUnavailable) as exc_info:
        ragas_evaluation.require_ragas_evaluation()

    assert "See issue #2043" in str(exc_info.value)
