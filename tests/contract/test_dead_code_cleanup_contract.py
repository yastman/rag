"""Contracts for DEPS-15 verified dead-code removals."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REMOVED_SYMBOLS = {
    "scripts/archive/git_hygiene.py": {
        "find_merged_branches",
        "find_no_upstream_branches",
        "find_stale_worktrees",
        "fix_merged_branches",
    },
    "src/observability_sentry.py": {"_resolve"},
    "src/models/contextualized_embedding.py": {"embed_queries_sync"},
}


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_verified_dead_code_symbols_are_removed() -> None:
    existing = {
        file: sorted(symbols & _function_names(ROOT / file))
        for file, symbols in REMOVED_SYMBOLS.items()
    }
    assert existing == {file: [] for file in REMOVED_SYMBOLS}
