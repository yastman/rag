"""Contract: duplicate-stale-code audit for issue #2711.

Enforces that the duplicate-stale-code bug class is registered in
.github/bug-classes.yml. The original scoring-shim identity check was retired
with the no-op scoring surface in #3331.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


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
