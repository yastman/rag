"""Contract: unified ingestion E2E test file is present and well-structured (#1629).

Retargeted from the deleted ``tests/integration/test_ingestion_e2e.py`` to
the live file ``tests/integration/test_unified_ingestion_e2e.py``.

The contract ensures:
- The live E2E test file exists and is importable (no syntax errors).
- It carries the correct pytest marks for service-gated tests
  (``requires_services`` / ``RUN_INTEGRATION_TESTS`` guard).
- It does not silently pass with no tests collected (the file must contain
  at least a fixture or test function — an empty file is a gap).
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "tests" / "integration" / "test_unified_ingestion_e2e.py"


def test_ingestion_e2e_assertions_target_file_exists() -> None:
    """Live E2E target file must exist (#1629 retarget)."""
    assert TARGET.exists(), (
        f"missing target: {TARGET.relative_to(REPO_ROOT)}. "
        "This is the live replacement for the deleted test_ingestion_e2e.py."
    )


def test_ingestion_e2e_target_is_valid_python() -> None:
    """Live E2E file must parse without syntax errors."""
    src = TARGET.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(TARGET))
    except SyntaxError as exc:
        raise AssertionError(f"{TARGET.relative_to(REPO_ROOT)} has a syntax error: {exc}") from exc


def test_ingestion_e2e_target_has_service_guard() -> None:
    """Live E2E file must guard tests behind ``RUN_INTEGRATION_TESTS`` or ``requires_services``."""
    src = TARGET.read_text(encoding="utf-8")
    has_guard = "RUN_INTEGRATION_TESTS" in src or "requires_services" in src
    assert has_guard, (
        f"{TARGET.relative_to(REPO_ROOT)} must guard tests behind "
        "RUN_INTEGRATION_TESTS env-var skip or a requires_services marker "
        "so they don't run in the default fast gate."
    )


def test_ingestion_e2e_target_is_not_empty() -> None:
    """Live E2E file must contain at least one fixture or test definition."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definitions, (
        f"{TARGET.relative_to(REPO_ROOT)} contains no function or class definitions. "
        "Add at least one fixture or test to prevent the E2E coverage gap."
    )
