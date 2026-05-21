"""Contract: only one canonical ``pytest_collection_modifyitems`` (***REMOVED***1515 D2).

The audit in ***REMOVED***1515 (D2) found that the directory-based auto-marker hook —
which lives in ``tests/conftest.py`` and walks ``path_to_marker`` to attach
``unit``/``integration``/``smoke``/``e2e``/``chaos``/``load``/``benchmark``/
``contract``/``baseline`` markers based on the test's filesystem location —
had been copy-pasted into six sub-conftest files (smoke, integration, e2e,
benchmark, chaos, load).

Why the duplicates are a maintenance hazard:

* Pytest's ``pytest_collection_modifyitems`` is a 1:N hook — every conftest
  in the lookup chain contributes an implementation and **all** of them run
  (Context7 confirms: "for any given hook specification there can be multiple
  implementations, leading to a 1:N function call scenario"). The sub-conftest
  copies are therefore not dead code; they re-apply the same path-based
  markers to an items list the root has already marked.
* When the root hook's ``path_to_marker`` dict learns a new lane (e.g.
  ``contract``/``baseline`` were added in ***REMOVED***1515 B5), every drifted copy
  silently keeps the old set, producing an inconsistent collection state
  depending on which conftest pytest chooses to invoke first.
* Moving marker logic also requires updating N+1 files instead of one.

This contract pins the cleanup so the duplicates cannot silently come back.
It walks every ``conftest.py`` under ``tests/`` with AST and asserts:

  1. The auto-marker pattern (a ``pytest_collection_modifyitems`` body that
     iterates ``items`` and attaches markers via ``item.add_marker`` based on
     a path lookup) appears in **exactly one** conftest, and that conftest
     is ``tests/conftest.py``.
  2. Any other ``pytest_collection_modifyitems`` definition that may be
     introduced later (for legitimate tier-specific reasons) must NOT match
     the auto-marker pattern — i.e. it is a thin, tier-specific override
     rather than another copy of the directory walk.

If a sub-conftest legitimately needs a tier-specific hook in the future, it
can still define ``pytest_collection_modifyitems``; this contract just
prevents another verbatim copy of the root's directory-based marker walk.

Refs ***REMOVED***1515 (D2).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"
ROOT_CONFTEST_REL = Path("tests") / "conftest.py"


def _iter_conftests() -> list[Path]:
    """Every ``conftest.py`` reachable under ``tests/``."""
    return sorted(TESTS_DIR.rglob("conftest.py"))


def _find_modifyitems_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Top-level (module-level) defs named ``pytest_collection_modifyitems``."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == "pytest_collection_modifyitems"
        ):
            found.append(node)
    return found


def _looks_like_auto_marker_walk(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Heuristic: does this function body re-implement the root path->marker walk?

    A function matches when its body contains BOTH:
      (a) at least one ``for ... in items`` (or ``in <name>`` where the name is
          the items parameter) loop, AND
      (b) at least one ``item.add_marker(...)`` call (any attribute named
          ``add_marker`` invoked on something).

    That captures the root pattern in ``tests/conftest.py``::

        for item in items:
            for directory, marker in path_to_marker.items():
                if directory in item_path.parents:
                    item.add_marker(getattr(pytest.mark, marker))

    A trivial tier-specific hook that, e.g., only forwards to a helper or
    only conditionally adds a single marker without iterating ``items`` will
    not trigger this check.
    """
    has_items_loop = False
    has_add_marker_call = False

    for node in ast.walk(func):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            has_items_loop = True
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute) and target.attr == "add_marker":
                has_add_marker_call = True

    return has_items_loop and has_add_marker_call


def _collect_definitions() -> list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef, bool]]:
    """Return ``(rel_path, func_node, looks_like_auto_marker)`` for every def found."""
    out: list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef, bool]] = []
    for conftest in _iter_conftests():
        try:
            tree = ast.parse(conftest.read_text(encoding="utf-8"), filename=str(conftest))
        except SyntaxError:  ***REMOVED*** pragma: no cover - defensive
            continue
        for func in _find_modifyitems_defs(tree):
            out.append(
                (
                    conftest.relative_to(REPO_ROOT),
                    func,
                    _looks_like_auto_marker_walk(func),
                )
            )
    return out


def test_pytest_collection_modifyitems_has_single_canonical_definition() -> None:
    """At most one conftest may carry the auto-marker walk, and it must be root (***REMOVED***1515 D2)."""
    definitions = _collect_definitions()
    auto_marker_locations = [rel for rel, _func, looks_auto in definitions if looks_auto]

    ***REMOVED*** 1. Exactly one auto-marker walk in the entire tests/ tree.
    assert len(auto_marker_locations) == 1, (
        "Exactly one conftest may implement the directory-based auto-marker "
        "walk in pytest_collection_modifyitems (the root tests/conftest.py is "
        "the single source of truth — see ***REMOVED***1515 D2). "
        f"Found {len(auto_marker_locations)} copies: "
        f"{[str(p) for p in auto_marker_locations]}"
    )

    ***REMOVED*** 2. That single copy must live at tests/conftest.py.
    only_location = auto_marker_locations[0]
    assert only_location == ROOT_CONFTEST_REL, (
        "The directory-based auto-marker walk must live at tests/conftest.py, "
        f"not at {only_location}. Move the path-to-marker logic back to the "
        "root conftest (see ***REMOVED***1515 D2)."
    )


def test_no_sub_conftest_duplicates_root_modifyitems() -> None:
    """No sub-conftest may define a hook that mirrors the root auto-marker shape (***REMOVED***1515 D2)."""
    definitions = _collect_definitions()
    offenders = [
        rel
        for rel, _func, looks_auto in definitions
        if looks_auto and rel != ROOT_CONFTEST_REL
    ]
    assert not offenders, (
        "Sub-conftest files must not re-implement the root's auto-marker walk. "
        "If you need a tier-specific marker, add it directly under the matching "
        "tests/<lane>/ directory and let tests/conftest.py handle the directory "
        "auto-tagging.\n\n"
        f"Offending conftests: {[str(p) for p in offenders]}"
    )


def test_root_conftest_has_canonical_modifyitems() -> None:
    """The root conftest must keep the canonical hook so the contract is enforceable."""
    root = REPO_ROOT / "tests" / "conftest.py"
    tree = ast.parse(root.read_text(encoding="utf-8"), filename=str(root))
    defs = _find_modifyitems_defs(tree)
    assert len(defs) == 1, (
        f"tests/conftest.py must define exactly one pytest_collection_modifyitems "
        f"(found {len(defs)})."
    )
    assert _looks_like_auto_marker_walk(defs[0]), (
        "tests/conftest.py::pytest_collection_modifyitems must keep its "
        "directory-based auto-marker walk (iterates items + calls "
        "item.add_marker). Refactors that drop the items loop or the "
        "add_marker call need a contract update too."
    )


@pytest.mark.parametrize(
    "src",
    [
        ***REMOVED*** canonical body
        """
import pytest
from pathlib import Path

def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.unit)
""",
        ***REMOVED*** canonical body via async-for / nested loop
        """
import pytest

def pytest_collection_modifyitems(items):
    for item in items:
        for directory, marker in {}.items():
            item.add_marker(getattr(pytest.mark, marker))
""",
    ],
)
def test_helper_detects_auto_marker_pattern(src: str) -> None:
    tree = ast.parse(src)
    func = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert _looks_like_auto_marker_walk(func) is True


@pytest.mark.parametrize(
    "src",
    [
        ***REMOVED*** no items loop
        """
def pytest_collection_modifyitems(items):
    return None
""",
        ***REMOVED*** loop but no add_marker
        """
def pytest_collection_modifyitems(items):
    for i in items:
        i.user_properties.append(("k", "v"))
""",
        ***REMOVED*** add_marker but no loop (single targeted tweak — allowed)
        """
import pytest
def pytest_collection_modifyitems(items):
    if items:
        items[0].add_marker(pytest.mark.slow)
""",
    ],
)
def test_helper_does_not_flag_trivial_or_targeted_hooks(src: str) -> None:
    tree = ast.parse(src)
    func = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert _looks_like_auto_marker_walk(func) is False
