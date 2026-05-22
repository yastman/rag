"""Contract: fast/profile/duration Makefile targets must select the same lane.

Background (issue #1795)
------------------------
The local fast-gate selection was inconsistent across `make` targets. Some
targets did not exclude optional-extras tests via ``$(PYTEST_REQUIRES_EXTRAS_IGNORE)``,
some omitted ``not slow``, and some omitted ``not requires_extras`` from the
marker expression. The result: ``test-profile`` / ``test-store-durations``
could measure a different test universe than ``test-unit``, and the
``test`` / ``test-fast`` / ``test-all-fast`` lanes drifted from the
canonical core unit lane.

The canonical owner is ``test-unit``::

    PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ \\
        $(PYTEST_REQUIRES_EXTRAS_IGNORE) -n auto --dist=worksteal -q \\
        --timeout=30 -m "not legacy_api and not requires_extras and not slow"

Every other fast/profile/duration target must:

1. include ``$(PYTEST_REQUIRES_EXTRAS_IGNORE)`` to skip optional-extra files
   before pytest tries to import them, and
2. use the canonical marker expression
   ``not legacy_api and not requires_extras and not slow``.

These checks are intentionally byte-level on the Makefile recipe so that
silent drift surfaces immediately.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

# Targets that SHARE the fast/local lane semantics with `test-unit`.
# `test-profile` and `test-store-durations` measure that same lane, so they
# must select identically.
FAST_LANE_TARGETS = (
    "test",
    "test-unit",
    "test-unit-loadscope",
    "test-fast",
    "test-all-fast",
    "test-profile",
    "test-store-durations",
)

CANONICAL_MARKER = "not legacy_api and not requires_extras and not slow"
EXTRAS_IGNORE_VAR = "$(PYTEST_REQUIRES_EXTRAS_IGNORE)"


def _read_makefile_text() -> str:
    assert MAKEFILE.exists(), f"Makefile missing at {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


def _extract_recipe(makefile_text: str, target: str) -> str:
    """Return the recipe body for a target.

    A recipe ends at the first blank line or at the next top-level rule.
    """
    pattern = re.compile(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t.*\n|\n)*?)(?=^[A-Za-z0-9_./%-]+:|^\Z)",
        re.MULTILINE,
    )
    match = pattern.search(makefile_text)
    assert match, f"Target `{target}` not found in Makefile"
    return match.group(1)


def _pytest_invocation(recipe: str) -> str:
    """Return the pytest invocation line(s) inside a recipe.

    Handles both single-line invocations and multi-line continuations.
    Returns the *concatenated* command text (without the leading tab).
    """
    lines = []
    in_pytest = False
    for raw in recipe.splitlines():
        line = raw.lstrip("\t")
        if "uv run pytest" in line or "pytest tests/" in line:
            in_pytest = True
            lines.append(line)
            if not line.rstrip().endswith("\\"):
                break
            continue
        if in_pytest:
            lines.append(line)
            if not line.rstrip().endswith("\\"):
                break
    assert lines, f"No pytest invocation found in recipe:\n{recipe}"
    return " ".join(s.rstrip(" \\").strip() for s in lines)


@pytest.mark.parametrize("target", FAST_LANE_TARGETS)
def test_fast_lane_target_uses_extras_ignore(target: str) -> None:
    """Every fast-lane target must reuse $(PYTEST_REQUIRES_EXTRAS_IGNORE).

    Skipping this variable causes pytest to try to import optional-extra
    test modules (FastAPI, RAGAS, voice, ingestion-unified, ...) before
    marker deselection. On a core install those imports either fail
    collection or get reported as skipped -- both wasteful in the local
    fast loop.
    """
    text = _read_makefile_text()
    recipe = _extract_recipe(text, target)
    invocation = _pytest_invocation(recipe)
    assert EXTRAS_IGNORE_VAR in invocation, (
        f"Target `{target}` must include `{EXTRAS_IGNORE_VAR}` to skip "
        f"optional-extra tests at collection time. Found:\n  {invocation}"
    )


@pytest.mark.parametrize("target", FAST_LANE_TARGETS)
def test_fast_lane_target_uses_canonical_marker(target: str) -> None:
    """Every fast-lane target must select the canonical marker expression."""
    text = _read_makefile_text()
    recipe = _extract_recipe(text, target)
    invocation = _pytest_invocation(recipe)

    # Match `-m "<expr>"` or `-m '<expr>'`
    marker_match = re.search(r"""-m\s+(["'])(?P<expr>[^"']*)\1""", invocation)
    assert marker_match, (
        f"Target `{target}` must pass an explicit `-m \"...\"` marker "
        f"expression. Found:\n  {invocation}"
    )
    expr = marker_match.group("expr").strip()
    assert expr == CANONICAL_MARKER, (
        f"Target `{target}` marker expression must be the canonical fast-lane "
        f"expression so profiling/duration data tracks the same suite as "
        f"`test-unit`.\n  expected: {CANONICAL_MARKER!r}\n  got:      {expr!r}"
    )


def test_pytest_requires_extras_ignore_definition_present() -> None:
    """The shared variable must remain defined (don't accidentally inline)."""
    text = _read_makefile_text()
    assert "PYTEST_REQUIRES_EXTRAS_IGNORE :=" in text or \
        "PYTEST_REQUIRES_EXTRAS_IGNORE ?=" in text, (
        "Expected `PYTEST_REQUIRES_EXTRAS_IGNORE` to be defined as a Make "
        "variable so all fast-lane targets share the single source of truth."
    )


def test_canonical_marker_appears_at_least_once() -> None:
    """Sanity guard: at least one target must carry the canonical marker.

    If this fails, either the canonical expression itself was renamed (and
    this contract needs to follow), or every fast-lane target lost it.
    """
    text = _read_makefile_text()
    assert CANONICAL_MARKER in text, (
        f"Canonical marker {CANONICAL_MARKER!r} no longer appears in the "
        f"Makefile -- the fast-lane definition was changed without updating "
        f"this contract."
    )
