"""Contract: ``ChunkingStrategy`` exposes only SDK-native strategies (#1235 slice).

Issue #1235 calls for migrating chunking to Docling ``HybridChunker``. The
deprecated ``FIXED_SIZE`` and ``SLIDING_WINDOW`` strategies emitted
``DeprecationWarning`` since #780 with the explicit message:

> "Use CocoIndex + Docling HybridChunker for production chunking."

Production code never reads them — only the chunker module itself and the
chunker unit tests do. Removing them is the smallest atomic step toward
fully replacing custom chunking with the SDK.

This contract test forbids reintroducing custom-strategy enum members
without an explicit decision to revert SDK-native chunking. Verified via
Context7 (`/docling/docling`): ``HybridChunker`` is the documented
replacement that respects token budgets and document structure (page
boundaries, headings, table cells).

Content was rephrased for compliance with licensing restrictions.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHUNKER_PY = REPO_ROOT / "src" / "ingestion" / "chunker.py"


def _enum_members(tree: ast.AST) -> set[str]:
    """Return enum member names defined in the ChunkingStrategy class."""
    members: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ChunkingStrategy":
            for body_node in node.body:
                if isinstance(body_node, ast.Assign):
                    for target in body_node.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                elif isinstance(body_node, ast.AnnAssign):
                    target = body_node.target
                    if isinstance(target, ast.Name):
                        members.add(target.id)
    return members


def test_chunking_strategy_does_not_expose_fixed_size() -> None:
    """``ChunkingStrategy.FIXED_SIZE`` was removed in #1235; do not reintroduce."""
    tree = ast.parse(CHUNKER_PY.read_text(encoding="utf-8"), filename=str(CHUNKER_PY))
    members = _enum_members(tree)
    assert "FIXED_SIZE" not in members, (
        "ChunkingStrategy.FIXED_SIZE was removed in the #1235 slice (it emitted "
        "DeprecationWarning since #780 and had no production callers). Use Docling "
        "HybridChunker via DoclingClient.chunk_file() instead. Re-introducing it "
        "requires removing this contract assertion AND wiring the strategy into a "
        "production code path, not just the test suite."
    )


def test_chunking_strategy_does_not_expose_sliding_window() -> None:
    """``ChunkingStrategy.SLIDING_WINDOW`` was removed in #1235; do not reintroduce."""
    tree = ast.parse(CHUNKER_PY.read_text(encoding="utf-8"), filename=str(CHUNKER_PY))
    members = _enum_members(tree)
    assert "SLIDING_WINDOW" not in members, (
        "ChunkingStrategy.SLIDING_WINDOW was removed in the #1235 slice. Same "
        "reasoning as FIXED_SIZE — see the docstring of this contract test."
    )


def test_chunker_does_not_define_deprecated_strategy_methods() -> None:
    """``_chunk_fixed_size`` and ``_chunk_sliding_window`` must be gone."""
    tree = ast.parse(CHUNKER_PY.read_text(encoding="utf-8"), filename=str(CHUNKER_PY))
    forbidden = {"_chunk_fixed_size", "_chunk_sliding_window"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in forbidden:
            found.append(node.name)
    assert not found, (
        f"Found deprecated chunking helpers {found} in {CHUNKER_PY.relative_to(REPO_ROOT)}. "
        f"Remove them per #1235; production code uses Docling HybridChunker via "
        f"DoclingClient.chunk_file()."
    )
