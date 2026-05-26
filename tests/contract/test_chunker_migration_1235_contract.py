"""Contract: ratchet for the legacy ``DocumentChunker`` migration (#1235).

Issue #1235 directs production code away from the deprecated
``DocumentChunker`` (FIXED_SIZE / SLIDING_WINDOW / SEMANTIC strategies)
toward Docling's :class:`HybridChunker` exposed via the new public
adapter :func:`src.ingestion.hybrid_chunker.make_hybrid_chunker`.

The migration is multi-PR (each call site has its own consumers and
config). This contract is the **ratchet** that keeps the migration
moving:

* ``CHUNKER_CALL_SITE_ALLOWLIST`` lists every file that constructs
  ``DocumentChunker(...)`` today.
* The contract fails when a new file introduces a forbidden constructor
  call (mirrors the layering ratchet in
  ``test_layering_no_telegram_bot_imports_contract.py``).
* The allowlist must shrink over time; never regenerate it to silence a
  failure.

Re-export entries (``__init__.py`` lines that simply expose
``DocumentChunker`` for back-compat) are not constructor calls and are
out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "src",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
    REPO_ROOT / "scripts",
)

# Files allowed to construct ``DocumentChunker(...)`` today.
# Frozen baseline — must shrink, never grow. Each entry should map to a
# tracked follow-up PR removing the call site.
CHUNKER_CALL_SITE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Legacy core RAG pipeline used by the evaluation script
        # (src/evaluation/ragas_evaluation.py imports RAGPipeline from here).
        # Migration to make_hybrid_chunker is tracked in #1235 follow-ups.
        "src/core/pipeline.py",
    }
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            spath = str(p)
            if "/.venv/" in spath or "/__pycache__/" in spath:
                continue
            files.append(p)
    return files


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _find_document_chunker_calls(tree: ast.AST) -> list[int]:
    """Return line numbers of bare ``DocumentChunker(...)`` constructor calls.

    Matches both ``DocumentChunker(...)`` and ``mod.DocumentChunker(...)``.
    """
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "DocumentChunker") or (
            isinstance(func, ast.Attribute) and func.attr == "DocumentChunker"
        ):
            found.append(node.lineno)
    return found


def test_no_new_document_chunker_call_sites() -> None:
    """New code must use ``make_hybrid_chunker`` instead of ``DocumentChunker``."""
    offenders: list[str] = []
    for py_file in _iter_python_files():
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if rel in CHUNKER_CALL_SITE_ALLOWLIST:
            continue
        # Skip the chunker module itself (defines the class).
        if rel == "src/ingestion/chunker.py":
            continue
        # Adapter module references the class only in docstrings.
        if rel == "src/ingestion/hybrid_chunker.py":
            continue
        tree = _parse(py_file)
        if tree is None:
            continue
        for lineno in _find_document_chunker_calls(tree):
            offenders.append(f"  {rel}:{lineno}")
    assert not offenders, (
        "#1235: new file(s) construct DocumentChunker(...). The legacy chunker "
        "is being replaced by Docling HybridChunker via "
        "src.ingestion.hybrid_chunker.make_hybrid_chunker(). Migrate the new "
        "call site instead of adding it to the allowlist.\nOffenders:\n" + "\n".join(offenders)
    )


def test_chunker_allowlist_paths_exist() -> None:
    """Allowlist entries must point to real files (catches drift on rename)."""
    missing = [rel for rel in CHUNKER_CALL_SITE_ALLOWLIST if not (REPO_ROOT / rel).exists()]
    assert not missing, (
        "#1235: known_allowlist points to missing files. Update the contract "
        f"after the migration / rename:\n  {missing}"
    )


def test_chunker_allowlist_entries_actually_use_pattern() -> None:
    """Stale allowlist entries are rejected — forces shrinkage as call sites
    are migrated to ``make_hybrid_chunker``."""
    stale: list[str] = []
    for rel in CHUNKER_CALL_SITE_ALLOWLIST:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        tree = _parse(path)
        if tree is None:
            continue
        if not _find_document_chunker_calls(tree):
            stale.append(f"  {rel} (no DocumentChunker(...) call remains)")
    assert not stale, (
        "#1235: stale allowlist entries — remove them from the contract:\n" + "\n".join(stale)
    )


def test_make_hybrid_chunker_is_publicly_importable() -> None:
    """The migration target must remain a stable public import."""
    from src.ingestion.hybrid_chunker import (  # noqa: F401
        chunks_to_chunk_objects,
        make_hybrid_chunker,
    )
