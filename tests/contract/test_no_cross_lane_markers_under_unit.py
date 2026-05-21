"""Contract: no foreign-lane markers (e.g. ``integration``) under ``tests/unit/`` (***REMOVED***1797).

``tests/conftest.py::pytest_collection_modifyitems`` injects directory-based
markers, so a test file under ``tests/unit/`` is tagged ``unit`` automatically.
If that same test also carries an explicit ``@pytest.mark.integration`` (or
``smoke``/``e2e``/``chaos``/``load``/``benchmark``/``baseline``) decorator, it
is collected by BOTH lanes. Fast-gate marker expressions like ``-m unit`` would
then run an integration-only scenario in the unit lane, increasing runtime and
producing xdist/shared-state surprises.

This contract walks ``tests/unit/`` with AST and fails when a test is decorated
with any non-unit lane marker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_DIR = REPO_ROOT / "tests" / "unit"

***REMOVED*** Markers attached automatically by directory in tests/conftest.py.
***REMOVED*** Anything in this set, used explicitly under tests/unit/, means the test
***REMOVED*** is being placed in the wrong lane.
FOREIGN_LANE_MARKERS = frozenset(
    {
        "integration",
        "smoke",
        "e2e",
        "chaos",
        "load",
        "benchmark",
        "baseline",
    }
)


def _decorator_marker_name(decorator: ast.expr) -> str | None:
    """Return ``X`` for ``@pytest.mark.X`` / ``@pytest.mark.X(...)``, else None."""
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not isinstance(node, ast.Attribute):
        return None
    parent = node.value
    if not isinstance(parent, ast.Attribute) or parent.attr != "mark":
        return None
    grandparent = parent.value
    if not isinstance(grandparent, ast.Name) or grandparent.id != "pytest":
        return None
    return node.attr


def _iter_test_definitions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if name.startswith(("test_", "Test")):
                yield node


def _collect_violations() -> list[tuple[Path, str, str]]:
    """Return ``(file, test_name, foreign_marker)`` tuples found under ``tests/unit/``."""
    violations: list[tuple[Path, str, str]] = []
    if not UNIT_DIR.exists():  ***REMOVED*** pragma: no cover - defensive
        return violations

    for path in sorted(UNIT_DIR.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  ***REMOVED*** pragma: no cover - parser is forgiving enough
            continue

        for definition in _iter_test_definitions(tree):
            for decorator in definition.decorator_list:
                marker = _decorator_marker_name(decorator)
                if marker in FOREIGN_LANE_MARKERS:
                    violations.append(
                        (path.relative_to(REPO_ROOT), definition.name, marker)
                    )
    return violations


def test_no_foreign_lane_markers_under_tests_unit() -> None:
    """No test under ``tests/unit/`` may carry a non-unit lane marker (***REMOVED***1797)."""
    violations = _collect_violations()
    if violations:
        formatted = "\n".join(
            f"  - {path}::{name} is decorated with @pytest.mark.{marker}"
            for path, name, marker in violations
        )
        raise AssertionError(
            "Tests under tests/unit/ must not carry foreign-lane markers "
            f"({sorted(FOREIGN_LANE_MARKERS)}).\n"
            "Move them to the matching tests/<lane>/ directory or remove the "
            "marker if the lane choice is wrong.\n\n"
            "Violations:\n"
            f"{formatted}"
        )


def test_foreign_lane_marker_set_is_synced_with_conftest() -> None:
    """If a new lane is added in tests/conftest.py, this contract must learn it."""
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    ***REMOVED*** Lanes appear as 'root / "<lane>": "<lane>",' in path_to_marker.
    ***REMOVED*** We only care about the value side (marker name).
    import re

    pairs = re.findall(r'root / "([a-z0-9]+)": "([a-z0-9]+)",', conftest)
    discovered = {marker for _path, marker in pairs}
    ***REMOVED*** `unit` is the home lane and must NOT be in the foreign set.
    expected_foreign = discovered - {"unit", "contract"}
    assert expected_foreign == FOREIGN_LANE_MARKERS, (
        "FOREIGN_LANE_MARKERS in this contract must match every non-unit, "
        "non-contract lane declared in tests/conftest.py::path_to_marker. "
        f"Contract has {sorted(FOREIGN_LANE_MARKERS)}, conftest has "
        f"{sorted(expected_foreign)}."
    )


@pytest.mark.parametrize("marker", sorted(FOREIGN_LANE_MARKERS))
def test_foreign_marker_helper_recognizes_pytest_mark(marker: str) -> None:
    """``_decorator_marker_name`` must recognize ``@pytest.mark.<marker>`` exactly."""
    src = f"import pytest\n\n@pytest.mark.{marker}\ndef test_x(): ...\n"
    tree = ast.parse(src)
    func = tree.body[1]
    assert isinstance(func, ast.FunctionDef)
    assert _decorator_marker_name(func.decorator_list[0]) == marker
