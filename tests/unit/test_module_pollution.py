"""Test that no global sys.modules pollution occurs during test runs.

Policy: NEVER assign to sys.modules at module level in test files.
Use ``monkeypatch.setitem(sys.modules, ...)`` inside fixtures, or register
mocks via ``pytest_configure`` in conftest.py for collection-time needs.
"""

import ast
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest


_TESTS_ROOT = Path(__file__).resolve().parents[1]  # tests/


def test_no_global_sys_modules_patching():
    """Verify tests don't pollute sys.modules at import time.

    All sys.modules mocking MUST be fixture-scoped, not global.
    Rationale:
    - Global patching affects test isolation
    - Prevents pytest-xdist from working correctly
    - Can cause flaky tests due to import order
    """
    # These modules should only exist if actually installed
    forbidden_mocks = [
        "redisvl",
        "redisvl.query",
        "redisvl.query.filter",
    ]

    for module_name in forbidden_mocks:
        if module_name in sys.modules:
            module = sys.modules[module_name]
            # Real redisvl has __file__ attribute
            if not hasattr(module, "__file__"):
                pytest.fail(
                    f"Global sys.modules mock detected: {module_name}. "
                    f"Use @pytest.fixture with monkeypatch instead."
                )


def test_langfuse_not_globally_mocked():
    """Langfuse mock must be fixture-scoped, not global."""
    if "langfuse" in sys.modules:
        module = sys.modules["langfuse"]
        # Real langfuse should be an importable module backed by a file.
        if not isinstance(module, ModuleType) or not getattr(module, "__file__", None):
            pytest.fail(
                "Global langfuse mock detected. Use @pytest.fixture(autouse=True) "
                "with monkeypatch.setitem(sys.modules, ...) instead."
            )


def test_prometheus_client_not_globally_mocked():
    """prometheus_client mock must be fixture-scoped, not global."""
    if "prometheus_client" in sys.modules:
        module = sys.modules["prometheus_client"]
        if isinstance(module, MagicMock):
            pytest.fail(
                "Global prometheus_client mock detected. "
                "Use @pytest.fixture with monkeypatch.setitem instead."
            )


def test_no_module_level_sys_modules_assignment():
    """Static guard: scan test files for module-level ``sys.modules[...] = ...``.

    Conftest files using ``pytest_configure`` are allowed.
    Assignments inside functions, fixtures, and classes are fine.
    Only bare module-level assignments are forbidden.
    """
    violations: list[str] = []

    for py_file in sorted(_TESTS_ROOT.rglob("*.py")):
        # conftest.py files may use pytest_configure for collection-time mocks
        if py_file.name == "conftest.py":
            continue

        source = py_file.read_text(encoding="utf-8")
        # Fast path: most files do not touch sys.modules at all.
        if "sys.modules[" not in source:
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
            # Only check top-level statements (module body)
            if not isinstance(node, (ast.Assign, ast.Expr)):
                continue

            source_line = ast.get_source_segment(source, node) or ""

            if "sys.modules[" in source_line and "=" in source_line:
                rel = py_file.relative_to(_TESTS_ROOT)
                violations.append(f"{rel}:{node.lineno}")

    if violations:
        pytest.fail(
            f"Module-level sys.modules assignment detected in {len(violations)} "
            f"location(s):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nUse monkeypatch.setitem(sys.modules, ...) in a fixture instead. "
            "See .claude/rules/testing.md § 'sys.modules hygiene'."
        )
