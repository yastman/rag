"""Contract: duplicate-stale-code audit for issue #2711.

Enforces that:
1. src/scoring.py is a shim re-exporting from src/observability/scores.py —
   no duplicate implementation. The public symbols resolve to the same objects.
2. The duplicate-stale-code bug class is registered in .github/bug-classes.yml.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_src_scoring_is_shim_of_observability_scores() -> None:
    """src/scoring.py must not redefine functions that live in src/observability/scores.py.

    The two files are currently byte-for-byte identical (#2711 audit).
    After the fix, src/scoring.py becomes a shim that imports from
    src/observability/scores.py so there is a single source of truth.
    """
    import src.observability.scores as scores_mod
    import src.scoring as scoring_mod

    for name in ("write_scores", "score", "compute_checkpointer_overhead_proxy_ms"):
        assert getattr(scoring_mod, name) is getattr(scores_mod, name), (
            f"src.scoring.{name} must be the same object as src.observability.scores.{name}. "
            "src/scoring.py should be a shim that re-exports from src/observability/scores.py "
            "(#2711 duplicate-stale-code audit)."
        )


def test_duplicate_stale_code_bug_class_registered() -> None:
    """The duplicate-stale-code bug class must be registered in .github/bug-classes.yml."""
    bug_classes_path = REPO_ROOT / ".github" / "bug-classes.yml"
    assert bug_classes_path.exists(), f"bug-classes.yml not found at {bug_classes_path}"
    data = yaml.safe_load(bug_classes_path.read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in data.get("bug_classes", [])}
    assert "duplicate-stale-code" in ids, (
        "Bug class 'duplicate-stale-code' must be registered in .github/bug-classes.yml "
        "(#2711 anti_regression_contract)."
    )
