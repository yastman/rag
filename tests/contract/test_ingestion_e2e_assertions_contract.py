"""Contract: ingestion E2E success-path tests must not accept errors or no-ops (***REMOVED***1629).

Three success-path assertions in
``tests/integration/test_ingestion_e2e.py`` previously passed when the
runtime returned an error dict or zero points:

- ``test_ingest_directory_creates_nodes``: ``points_count >= 0`` accepts
  a no-op ingestion as success.
- ``test_get_collection_stats``: ``"name" in stats or "error" in stats``
  accepts an error response as success.
- ``test_get_ingestion_status``: same shape — error reported as success.

Negative tests like ``test_ingest_gdrive_without_credentials_fails_gracefully``
must remain unchanged. This contract uses AST inspection to keep the
distinction sharp: success-path tests must require ``"error" not in ...``
and a positive point count, while negative tests are exempt.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "tests" / "integration" / "test_ingestion_e2e.py"

***REMOVED*** Tests known to be negative-path / graceful-failure assertions; they MAY
***REMOVED*** accept an "error" key. Everything else under TestIngestion*E2E is treated
***REMOVED*** as a success-path test.
NEGATIVE_TESTS: frozenset[str] = frozenset(
    {
        "test_ingest_gdrive_without_credentials_fails_gracefully",
    }
)


def _iter_test_methods(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            yield node


def _assert_sources(func: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            try:
                out.append(ast.unparse(node.test))
            except Exception:  ***REMOVED*** pragma: no cover
                pass
    return out


def test_target_file_exists() -> None:
    assert TARGET.exists(), f"missing target: {TARGET}"


def test_success_path_assertions_require_positive_points() -> None:
    """``test_ingest_directory_creates_nodes`` must require ``points_count > 0`` (***REMOVED***1629)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    func = next(
        f for f in _iter_test_methods(tree) if f.name == "test_ingest_directory_creates_nodes"
    )
    sources = _assert_sources(func)
    has_positive_points = any(
        "points_count" in src and (">= 1" in src or "> 0" in src) for src in sources
    )
    assert has_positive_points, (
        "test_ingest_directory_creates_nodes must assert "
        "points_count > 0 (or >= 1) after a successful ingestion. "
        f"Found assertions: {sources!r}"
    )

    has_lax_points = any("points_count" in src and ">= 0" in src for src in sources)
    assert not has_lax_points, (
        "test_ingest_directory_creates_nodes must NOT assert "
        "points_count >= 0 — that accepts a no-op ingestion as success."
    )


def test_success_path_assertions_forbid_error_key_acceptance() -> None:
    """Success-path tests must assert ``error not in ...`` instead of allowing it (***REMOVED***1629)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))

    violations: list[str] = []
    for func in _iter_test_methods(tree):
        if func.name in NEGATIVE_TESTS:
            continue
        for src in _assert_sources(func):
            ***REMOVED*** Bug pattern: "name" in X or "error" in X — accepts error as success.
            if "'error' in" in src.replace('"', "'") and "'name' in" in src.replace('"', "'"):
                if " or " in src:
                    violations.append(f"{func.name}: {src}")
    assert not violations, (
        "Success-path E2E tests must NOT accept an 'error' key as success. "
        "Move graceful-failure shape checks into a dedicated negative test "
        "(see test_ingest_gdrive_without_credentials_fails_gracefully).\n"
        "Violations:\n  - " + "\n  - ".join(violations)
    )


def test_success_path_assertions_require_no_error_key() -> None:
    """The success-path tests must positively assert ``"error" not in <stats>`` (***REMOVED***1629)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    expected_to_assert_no_error = {
        "test_ingest_directory_creates_nodes",
        "test_get_collection_stats",
        "test_get_ingestion_status",
    }
    missing: list[str] = []
    for func in _iter_test_methods(tree):
        if func.name not in expected_to_assert_no_error:
            continue
        sources = _assert_sources(func)
        ***REMOVED*** Accept either '"error" not in stats' or "error" not in collection_stats.
        has_no_error = any(
            "'error' not in" in src.replace('"', "'") for src in sources
        )
        if not has_no_error:
            missing.append(f"{func.name}: {sources}")
    assert not missing, (
        "Success-path tests must assert 'error' not in <stats>. Missing in:\n"
        "  - " + "\n  - ".join(missing)
    )


def test_negative_test_kept_intact() -> None:
    """Negative-path test must still exist and still check graceful failure (***REMOVED***1629)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    names = {f.name for f in _iter_test_methods(tree)}
    assert (
        "test_ingest_gdrive_without_credentials_fails_gracefully" in names
    ), "Refactor must not remove the dedicated negative-path test"
