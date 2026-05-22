"""Contract tests for issue #1083: sparse vector name must match collection schema.

The unified ingestion pipeline creates the Qdrant collection with the
sparse vector named ``bm42`` (see ``src/ingestion/unified/cli.py``::

    sparse_vectors_config = {"bm42": SparseVectorParams(modifier=Modifier.IDF)}

Per Qdrant Python Client docs (Context7 ``/qdrant/qdrant-client``),
``client.query_points(... using="<name>", ...)`` and
``models.Prefetch(... using="<name>", ...)`` require ``<name>`` to match
the named vector in the collection. Using a different name produces::

    gRPC /qdrant.Points/Query failed with
    Client specified an invalid argument
    "Wrong input: Not existing vector name error: \"sparse\""

— exactly the error captured in issue #1083.

These tests guard the contract by parsing the AST of any production
module that issues Qdrant queries and asserting it never uses
``using="sparse"``. The single legal sparse vector name in this repo
is ``"bm42"``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

# Modules that issue Qdrant queries against the canonical collection
# (gdrive_documents_bge / mirrored eval collections). Tests and scripts
# that build their *own* schema with a different name (e.g. throwaway
# in-memory ":memory:" collections) are intentionally excluded.
SCAN_FILES: tuple[Path, ...] = (
    REPO_ROOT / "src" / "evaluation" / "search_engines.py",
    REPO_ROOT / "src" / "retrieval" / "search_engines.py",
    REPO_ROOT / "telegram_bot" / "services" / "qdrant.py",
    REPO_ROOT / "telegram_bot" / "services" / "apartments_service.py",
)

CANONICAL_SPARSE_VECTOR_NAME = "bm42"


def _iter_using_keywords(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, value)`` for every ``using=<str>`` keyword arg."""
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "using":
                continue
            value = kw.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                hits.append((kw.value.lineno, value.value))
    return hits


@pytest.mark.parametrize("module_path", SCAN_FILES, ids=lambda p: p.name)
def test_no_using_sparse_in_production_qdrant_queries(module_path: Path) -> None:
    """No production Qdrant query may use ``using="sparse"`` — issue #1083.

    The collection created by the unified ingestion pipeline names the
    sparse vector ``"bm42"``, so any caller that queries with
    ``using="sparse"`` triggers a Wrong input gRPC error.
    """
    assert module_path.exists(), f"Expected {module_path} to exist"
    source = module_path.read_text(encoding="utf-8")
    offenders = [
        (lineno, value) for lineno, value in _iter_using_keywords(source) if value == "sparse"
    ]
    assert not offenders, (
        f'{module_path.relative_to(REPO_ROOT)} uses ``using="sparse"`` at '
        f"{[lineno for lineno, _ in offenders]!r}. The canonical sparse vector "
        f"name in the repo is {CANONICAL_SPARSE_VECTOR_NAME!r} — see issue #1083 "
        "and src/ingestion/unified/cli.py for the schema."
    )


@pytest.mark.parametrize("module_path", SCAN_FILES, ids=lambda p: p.name)
def test_sparse_using_keyword_is_canonical_name(module_path: Path) -> None:
    """Every sparse-vector ``using=...`` must use the canonical name.

    A future refactor that introduces a new name (e.g. ``"sparse_v2"``)
    must also update the ingestion schema; this test fails-loud when
    the names drift apart.
    """
    assert module_path.exists()
    source = module_path.read_text(encoding="utf-8")
    # We only flag values that look like sparse-vector names. The dense
    # path uses ``"dense"``, the multi-vector ColBERT path uses
    # ``"colbert"`` — those are valid and should not be touched.
    sparse_like_values = {
        value
        for _, value in _iter_using_keywords(source)
        if "sparse" in value or "bm" in value.lower()
    }
    illegal = sparse_like_values - {CANONICAL_SPARSE_VECTOR_NAME}
    assert not illegal, (
        f"{module_path.relative_to(REPO_ROOT)} uses non-canonical sparse "
        f"vector name(s): {sorted(illegal)!r}. Only "
        f"{CANONICAL_SPARSE_VECTOR_NAME!r} is registered in the unified "
        "ingestion pipeline schema (issue #1083)."
    )


def test_canonical_sparse_name_matches_ingestion_schema() -> None:
    """Sanity guard: ``CANONICAL_SPARSE_VECTOR_NAME`` must match the schema
    declared by the unified ingestion CLI."""
    cli_path = REPO_ROOT / "src" / "ingestion" / "unified" / "cli.py"
    assert cli_path.exists(), f"Expected {cli_path} to exist"
    text = cli_path.read_text(encoding="utf-8")
    assert re.search(
        rf'"\b{re.escape(CANONICAL_SPARSE_VECTOR_NAME)}\b"\s*:\s*SparseVectorParams',
        text,
    ), (
        f"src/ingestion/unified/cli.py no longer registers "
        f"{CANONICAL_SPARSE_VECTOR_NAME!r} as the sparse vector name. "
        "Update CANONICAL_SPARSE_VECTOR_NAME in this contract test "
        "AND every place that queries the collection."
    )
