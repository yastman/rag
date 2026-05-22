"""Contract: all first-class Python packages must be covered by lint targets.

Background (issue #1949)
------------------------
The Makefile targets used as the local quality gate were scoped narrowly to
``src/`` and ``telegram_bot/`` only. ``mini_app/``, ``services/``, and
``scripts/`` are first-class Python packages with production code but were
not linted by ``make lint`` or any of the other quality targets.

A ``LINT_PATHS`` variable was introduced to act as a single source of truth
for the scope.  All lint/format/type-check/security targets must reference
``$(LINT_PATHS)`` so the scope stays unified.  The CI workflow
(``.github/workflows/ci.yml``) must mirror the same set of paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

LINT_PATHS_EXPECTED = ["src/", "telegram_bot/", "mini_app/", "services/", "scripts/"]

LINT_TARGETS = [
    "lint",
    "lint-fix",
    "format",
    "format-check",
    "type-check",
    "pylint",
    "security",
    "dead-code",
]


def _read_makefile_text() -> str:
    assert MAKEFILE.exists(), f"Makefile missing at {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


def _extract_recipe(makefile_text: str, target: str) -> str:
    """Return the recipe body for a target.

    A recipe ends at the next top-level rule or end of file.
    """
    pattern = re.compile(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t.*\n|\n)*?)(?=^[A-Za-z0-9_./%-]+:|^\Z)",
        re.MULTILINE,
    )
    match = pattern.search(makefile_text)
    assert match, f"Target `{target}` not found in Makefile"
    return match.group(1)


# ---- Makefile variable definition ----


def test_lint_paths_variable_defined() -> None:
    """LINT_PATHS must be defined with exactly the expected paths."""
    text = _read_makefile_text()
    match = re.search(r"^LINT_PATHS\s*:=\s*(.+)$", text, re.MULTILINE)
    assert match is not None, (
        "LINT_PATHS variable not found in Makefile. "
        "Expected: LINT_PATHS := src/ telegram_bot/ mini_app/ services/ scripts/"
    )
    defined_paths = match.group(1).split()
    for path in LINT_PATHS_EXPECTED:
        assert path in defined_paths, (
            f"LINT_PATHS is missing '{path}'. "
            f"Defined paths: {defined_paths}"
        )
    assert set(defined_paths) == set(LINT_PATHS_EXPECTED), (
        f"LINT_PATHS contains unexpected paths. "
        f"Expected: {sorted(LINT_PATHS_EXPECTED)}, "
        f"Got: {sorted(defined_paths)}. "
        f"Update LINT_PATHS_EXPECTED in this contract test if a new path is intentional."
    )


# ---- Makefile targets use $(LINT_PATHS) ----


@pytest.mark.parametrize("target", LINT_TARGETS)
def test_target_uses_lint_paths_variable(target: str) -> None:
    """Each lint/format/security target must reference $(LINT_PATHS)."""
    text = _read_makefile_text()
    recipe = _extract_recipe(text, target)
    assert "$(LINT_PATHS)" in recipe, (
        f"Target `{target}` does not use $(LINT_PATHS) in its recipe. "
        f"All lint targets must reference the shared variable so scope "
        f"stays unified.\nRecipe:\n{recipe}"
    )


# ---- CI workflow mirrors the same paths ----


def _read_ci_text() -> str:
    assert CI_WORKFLOW.exists(), f"CI workflow missing at {CI_WORKFLOW}"
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_ci_ruff_check_covers_all_paths() -> None:
    """The CI Ruff lint step must reference all lint paths."""
    text = _read_ci_text()
    # Find the ruff check line
    match = re.search(r"run:\s*uvx ruff check (.+)", text)
    assert match is not None, "Ruff check step not found in ci.yml"
    check_line = match.group(1)
    for path in LINT_PATHS_EXPECTED:
        assert path in check_line, (
            f"CI ruff check step is missing '{path}'. Line: {match.group(0)}"
        )


def test_ci_ruff_format_covers_all_paths() -> None:
    """The CI Ruff format check step must reference all lint paths."""
    text = _read_ci_text()
    # Find the ruff format line
    match = re.search(r"run:\s*uvx ruff format (.+)", text)
    assert match is not None, "Ruff format step not found in ci.yml"
    format_line = match.group(1)
    for path in LINT_PATHS_EXPECTED:
        assert path in format_line, (
            f"CI ruff format step is missing '{path}'. Line: {match.group(0)}"
        )
