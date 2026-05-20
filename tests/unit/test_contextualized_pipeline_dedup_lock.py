"""Regression lock: contextualized pipeline test was duplicated (closes #1782).

``tests/integration/test_contextualized_pipeline.py`` was a byte-identical
duplicate of ``tests/unit/models/test_contextualized_pipeline.py``. Both
copies were skipped collection-wide before #1775 because they imported
``voyageai`` at module import time.

Once the unit copy was guarded with ``pytest.importorskip('voyageai')``
plus ``pytest.mark.requires_extras``, the integration copy added zero
coverage, ran no live services, and merely doubled the maintenance
surface. #1782 calls for "remove or guard duplicate".

Decision: **remove**. The integration tier should host tests that
actually exercise live services (Qdrant, Voyage API, etc.). A duplicate
of a guarded unit test does not qualify; reintroducing it should require
a fresh decision documented in the issue or a follow-up plan.

This lock prevents accidental re-introduction (e.g., via cherry-pick
from a stale branch).
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DUPLICATE_PATH = REPO_ROOT / "tests" / "integration" / "test_contextualized_pipeline.py"
UNIT_PATH = REPO_ROOT / "tests" / "unit" / "models" / "test_contextualized_pipeline.py"


def test_integration_duplicate_was_removed() -> None:
    """The integration-tier duplicate must stay deleted (#1782)."""
    assert not DUPLICATE_PATH.exists(), (
        f"{DUPLICATE_PATH.relative_to(REPO_ROOT)} reappeared. It was a "
        f"byte-identical duplicate of the unit test and was removed in "
        f"#1782. If a real integration test for the contextualized "
        f"pipeline is needed, write one that hits live services and "
        f"document the decision before re-introducing this filename."
    )


def test_unit_test_file_still_exists() -> None:
    """The canonical unit test is the surviving copy."""
    assert UNIT_PATH.exists(), (
        f"{UNIT_PATH.relative_to(REPO_ROOT)} is the canonical "
        f"contextualized-pipeline test and must not be removed; only the "
        f"integration-tier duplicate was deleted (#1782)."
    )
    text = UNIT_PATH.read_text(encoding="utf-8")
    # Smoke check: file remains a non-trivial test for the pipeline.
    assert len(text) > 1000, "unit test shrank unexpectedly; #1782 lock"
    assert "ContextualizedEmbeddingService" in text, (
        "unit test no longer references ContextualizedEmbeddingService; #1782 / #1773 contract"
    )
