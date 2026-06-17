"""Evaluation package coverage for the disabled RAGAS lane (#2043)."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.requires_extras("evaluation")

from src.evaluation.ragas_evaluation import RAGASEvaluationUnavailable, run_ragas_evaluation


@pytest.mark.asyncio
async def test_run_ragas_evaluation_is_explicitly_disabled() -> None:
    """Async callers should receive the same clear disabled-lane error."""
    with pytest.raises(RAGASEvaluationUnavailable, match="RAGAS evaluation is disabled"):
        await run_ragas_evaluation()
