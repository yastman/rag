"""Legacy filename retained for #2043 RAGAS dependency-removal coverage."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.requires_extras("evaluation")

from src.evaluation.ragas_evaluation import RAGAS_UNAVAILABLE_MESSAGE


def test_legacy_ragas_eval_surface_points_to_2043() -> None:
    """The old evaluate-with-ragas surface is intentionally not active."""
    assert "issue #2043" in RAGAS_UNAVAILABLE_MESSAGE
