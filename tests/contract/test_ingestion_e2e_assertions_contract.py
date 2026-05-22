"""Contract: ingestion E2E success-path tests must not accept errors or no-ops (#1629).

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
from contextlib import suppress
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "tests" / "integration" / "test_ingestion_e2e.py"

# Tests known to be negative-path / graceful-failure assertions; they MAY
# accept an "error" key. Everything else under TestIngestion*E2E is treated
# as a success-path test.
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
            with suppress(Exception):
                out.append(ast.unparse(node.test))
    return out


def _test_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for func in _iter_test_methods(tree):
        if func.name == name:
            return func
    raise AssertionError(f"test function {name!r} not found")


def _argument_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = [
        *func.args.posonlyargs,
        *func.args.args,
        *func.args.kwonlyargs,
    ]
    return {arg.arg for arg in args}


def test_ingestion_e2e_assertions_target_file_exists() -> None:
    assert TARGET.exists(), f"missing target: {TARGET}"


def test_success_path_assertions_require_positive_points() -> None:
    """``test_ingest_directory_creates_nodes`` must require ``points_count > 0`` (#1629)."""
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
    """Success-path tests must assert ``error not in ...`` instead of allowing it (#1629)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))

    violations: list[str] = []
    for func in _iter_test_methods(tree):
        if func.name in NEGATIVE_TESTS:
            continue
        for src in _assert_sources(func):
            # Bug pattern: "name" in X or "error" in X — accepts error as success.
            if (
                "'error' in" in src.replace('"', "'")
                and "'name' in" in src.replace('"', "'")
                and " or " in src
            ):
                violations.append(f"{func.name}: {src}")
    assert not violations, (
        "Success-path E2E tests must NOT accept an 'error' key as success. "
        "Move graceful-failure shape checks into a dedicated negative test "
        "(see test_ingest_gdrive_without_credentials_fails_gracefully).\n"
        "Violations:\n  - " + "\n  - ".join(violations)
    )


def test_success_path_assertions_require_no_error_key() -> None:
    """The success-path tests must positively assert ``"error" not in <stats>`` (#1629)."""
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
        # Accept either '"error" not in stats' or "error" not in collection_stats.
        has_no_error = any(
            "'error' not in" in src.replace('"', "'") for src in sources
        )
        if not has_no_error:
            missing.append(f"{func.name}: {sources}")
    assert not missing, (
        "Success-path tests must assert 'error' not in <stats>. Missing in:\n"
        "  - " + "\n  - ".join(missing)
    )


def test_success_path_status_tests_arrange_seed_data_before_asserting() -> None:
    """Stats/status success-path tests must create or depend on seeded Qdrant data."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    expected_to_seed = {
        "test_get_collection_stats",
        "test_get_ingestion_status",
    }
    missing: list[str] = []
    for name in expected_to_seed:
        func = _test_function(tree, name)
        args = _argument_names(func)
        body = ast.unparse(func)
        has_seed_fixture = "seeded_ingestion_collection" in args
        seeds_inline = "_seed_ingestion_collection" in body or ".ingest_directory(" in body
        if not has_seed_fixture and not seeds_inline:
            missing.append(name)

    assert not missing, (
        "Success-path stats/status tests must arrange a populated test "
        "collection before asserting 'error' not in stats. Otherwise they "
        "only pass when another test happened to run first. Missing seed "
        "setup in: " + ", ".join(missing)
    )


def test_get_ingestion_status_uses_seeded_test_collection() -> None:
    """The status E2E must not assert success against the default collection."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    func = _test_function(tree, "test_get_ingestion_status")
    calls = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_ingestion_status"
    ]
    assert calls, "test_get_ingestion_status must call get_ingestion_status"
    assert all(call.args or call.keywords for call in calls), (
        "test_get_ingestion_status must pass the seeded test collection name "
        "to get_ingestion_status(...). Calling it without arguments checks "
        "the default 'documents' collection and makes the test environment-dependent."
    )


def test_negative_test_kept_intact() -> None:
    """Negative-path test must still exist and still check graceful failure (#1629)."""
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    names = {f.name for f in _iter_test_methods(tree)}
    assert (
        "test_ingest_gdrive_without_credentials_fails_gracefully" in names
    ), "Refactor must not remove the dedicated negative-path test"
