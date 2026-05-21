# tests/contract/test_smoke_test_real_module_contract.py
"""Contract: tests/unit/evaluation/test_smoke_test.py exercises the real
``src.evaluation.smoke_test`` module instead of validating copied placeholder
constants and helper logic.

Closes #1619.

Two failure modes the audit found:
1. The real module had an import strategy that made it look not-importable, so
   the unit tests rebuilt local copies of ``SMOKE_QUERIES``, ``SLO_THRESHOLDS``,
   and percentile/violation logic. Those local copies happily passed while the
   real module could regress unobserved.
2. The unit test docstring even acknowledged that "smoke_test.py has relative
   imports that may not work in test context" — the test was wired to never
   protect the real module.

This contract makes the wiring explicit: real module must be importable from a
package path, and the unit test file must consume those real symbols.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_TEST_PATH = REPO_ROOT / "tests" / "unit" / "evaluation" / "test_smoke_test.py"


def test_real_smoke_test_module_is_importable_as_package_path() -> None:
    """The real module must be importable as ``src.evaluation.smoke_test``."""
    module = importlib.import_module("src.evaluation.smoke_test")

    assert hasattr(module, "SMOKE_QUERIES"), (
        "src.evaluation.smoke_test must expose SMOKE_QUERIES at module level"
    )
    assert hasattr(module, "SLO_THRESHOLDS"), (
        "src.evaluation.smoke_test must expose SLO_THRESHOLDS at module level"
    )
    assert hasattr(module, "run_smoke_test"), (
        "src.evaluation.smoke_test must expose run_smoke_test at module level"
    )


def test_real_smoke_queries_shape() -> None:
    """The real ``SMOKE_QUERIES`` constant must keep its documented shape."""
    module = importlib.import_module("src.evaluation.smoke_test")

    queries = module.SMOKE_QUERIES
    assert len(queries) == 30, f"SMOKE_QUERIES must have 30 entries, got {len(queries)}"

    difficulties = [q["difficulty"] for q in queries]
    assert difficulties.count("hard") == 10
    assert difficulties.count("medium") == 10
    assert difficulties.count("easy") == 10

    ids = [q["id"] for q in queries]
    assert len(ids) == len(set(ids)), "SMOKE_QUERIES ids must be unique"

    valid_types = {"paraphrased", "semantic", "direct"}
    for q in queries:
        for required_field in ("id", "query", "expected_article", "difficulty", "type"):
            assert required_field in q, (
                f"smoke query missing required field {required_field!r}: {q!r}"
            )
        assert q["type"] in valid_types, (
            f"smoke query has unknown type {q['type']!r}: {q!r}"
        )


def test_real_slo_thresholds_shape() -> None:
    """The real ``SLO_THRESHOLDS`` constant must keep documented keys/values."""
    module = importlib.import_module("src.evaluation.smoke_test")

    thresholds = module.SLO_THRESHOLDS
    assert thresholds["precision_at_1_min"] == 0.90
    assert thresholds["recall_at_10_min"] == 0.95
    assert thresholds["p95_latency_ms_max"] == 800
    assert thresholds["p99_latency_ms_max"] == 1200
    assert thresholds["failure_rate_max"] == 0.0


def _ast_walk(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_unit_test_imports_real_module() -> None:
    """The unit test file must import the real module — not redeclare it."""
    assert UNIT_TEST_PATH.exists(), f"missing {UNIT_TEST_PATH}"

    tree = _ast_walk(UNIT_TEST_PATH)
    imported_real_module = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.evaluation.smoke_test":
            imported_real_module = True
            break

    assert imported_real_module, (
        "tests/unit/evaluation/test_smoke_test.py must import from "
        "src.evaluation.smoke_test (not redeclare local placeholder copies)."
    )


def test_unit_test_does_not_redeclare_real_constants() -> None:
    """The unit test file must not contain local placeholder copies of
    ``SMOKE_QUERIES`` or ``SLO_THRESHOLDS``."""
    tree = _ast_walk(UNIT_TEST_PATH)

    forbidden = {"SMOKE_QUERIES", "SLO_THRESHOLDS"}
    for node in ast.walk(tree):
        # Class-level or module-level assignments to forbidden names.
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]

        for target in targets:
            name: str | None = None
            if isinstance(target, ast.Name):
                name = target.id
            elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                # `self.SMOKE_QUERIES = ...` is also forbidden.
                name = target.attr
            if name in forbidden:
                raise AssertionError(
                    f"tests/unit/evaluation/test_smoke_test.py redeclares {name}; "
                    "import it from src.evaluation.smoke_test instead."
                )


def test_unit_test_docstring_no_longer_disclaims_real_module() -> None:
    """The docstring used to say "may not work in test context", which signaled
    the test was ratcheted to placeholder data. Once the real module is wired
    that disclaimer must be gone."""
    src = UNIT_TEST_PATH.read_text(encoding="utf-8")
    assert "may not work in test context" not in src, (
        "Stale disclaimer about smoke_test imports still present in unit test."
    )
