"""Contracts for DEPS-15 verified dead-code removals."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REMOVED_FILES = {
    "scripts/log_correlation.py",
    "src/observability_sentry.py",
    "telegram_bot/observability_sentry.py",
    "telegram_bot/metrics_server.py",
    "src/models/contextualized_embedding.py",
    "src/utils/structure_parser.py",
}

REMOVED_SYMBOLS = {
    "scripts/archive/git_hygiene.py": {
        "find_merged_branches",
        "find_no_upstream_branches",
        "find_stale_worktrees",
        "fix_merged_branches",
    },
    "archive/evaluation/langfuse_integration.py": {"trace_search_with_spans"},
    "src/ingestion/docling_client.py": {"convert_file"},
    "src/runtime/config.py": {"create_hybrid_embeddings"},
    "src/runtime/pipeline/rag.py": {
        "_detect_filter_sensitive_query",
        "_expand_short_query",
    },
}


def _function_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    tree = ast.parse(path.read_text())
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_verified_dead_code_files_are_removed() -> None:
    existing = sorted(file for file in REMOVED_FILES if (ROOT / file).exists())
    assert existing == []


def test_verified_dead_code_symbols_are_removed() -> None:
    existing = {
        file: sorted(symbols & _function_names(ROOT / file))
        for file, symbols in REMOVED_SYMBOLS.items()
    }
    assert existing == {file: [] for file in REMOVED_SYMBOLS}
