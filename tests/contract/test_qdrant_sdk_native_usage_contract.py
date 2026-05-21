"""Contract test: lock SDK-native Qdrant usage in core retrieval / ingestion modules.

Several earlier issues (#1647 partially closed by #1751; #1846 build-then-delete
via HasIdCondition; the score-boosting consolidation around #590) converged on a
single rule: in the modules listed below, search and delete must go through the
canonical Qdrant Python client surface — never re-implemented as custom helpers
or older deprecated entry points.

Canonical SDK shapes (Context7-verified against /qdrant/qdrant-client; content
paraphrased for licensing compliance, ≤30 consecutive words from any source):

* Hybrid search uses ``client.query_points(...)`` with ``models.RrfQuery(rrf=Rrf(k=...))``
  (RRF) or ``models.FusionQuery(fusion=models.Fusion.DBSF)`` (DBSF) over a list
  of ``models.Prefetch`` stages — never custom Python-side rank fusion.
* The deprecated ``client.search(...)`` entry point is replaced by
  ``client.query_points(...)`` for all dense / sparse / fusion queries.
* Server-side score boosting uses ``models.FormulaQuery`` — not a private
  ``_score_boost`` Python helper.

This test scans the five files where these patterns concentrate. It must
trivially pass today and stay green forever; any new offender is a contract
regression.

Refs #1538, #1647, #1751, #1846, #590.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The five files where Qdrant SDK calls live — keep this list in sync with the
# audit issue (#1538). Adding a new core retrieval / ingestion file? Extend
# this list rather than working around the contract.
SCAN_FILES: list[Path] = [
    REPO_ROOT / "src" / "ingestion" / "unified" / "qdrant_writer.py",
    REPO_ROOT / "telegram_bot" / "services" / "apartments_service.py",
    REPO_ROOT / "telegram_bot" / "services" / "qdrant.py",
    REPO_ROOT / "src" / "retrieval" / "search_engines.py",
    REPO_ROOT / "src" / "evaluation" / "search_engines.py",
]

# Substrings that flag a custom rank-fusion or score-boost helper. The Qdrant
# server-side primitives (``RrfQuery`` / ``FusionQuery`` / ``FormulaQuery``)
# already cover every legitimate case; a Python function whose name contains
# any of these tokens is almost certainly re-implementing the SDK in user code.
FORBIDDEN_FN_NAME_TOKENS: tuple[str, ...] = (
    "_compute_rrf",
    "_custom_rrf",
    "_score_boost",
)

# Allowlist of function names that legitimately contain a forbidden token but
# are SDK-native at the call level. Kept small and justified per entry.
ALLOWED_FN_NAMES: frozenset[str] = frozenset(
    {
        # Public method on QdrantService that delegates server-side boosting to
        # ``models.FormulaQuery`` + ``ExpDecayExpression`` (Qdrant 1.14+); not a
        # custom Python helper. Tracked under #590.
        "search_with_score_boosting",
    }
)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _attribute_chain(node: ast.AST) -> str:
    """Return a dotted source-level representation of an attribute chain.

    For ``self._client.search`` returns ``"self._client.search"``. Falls back
    to ``ast.unparse`` when the chain contains non-trivial nodes (Subscript,
    Call, etc.) so that downstream substring checks remain reliable.
    """
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover — defensive, ast.unparse is total in 3.10+
        return ""


def _iter_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _iter_function_defs(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


# ---------------------------------------------------------------------------
# Individual rule scanners
# ---------------------------------------------------------------------------


def _find_fusion_rrf_literals(tree: ast.AST, file_path: Path) -> list[tuple[Path, int, str]]:
    """Flag ``models.Fusion.RRF`` / ``Fusion.RRF`` attribute access.

    The current canonical RRF wrapper is ``models.RrfQuery(rrf=models.Rrf(k=...))``.
    The legacy ``FusionQuery(fusion=models.Fusion.RRF)`` form is functionally
    equivalent but discouraged: ``RrfQuery`` exposes the ``k`` parameter
    explicitly and is what the rest of this codebase converged on after #1751.
    """
    offenders: list[tuple[Path, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "RRF":
            chain = _attribute_chain(node)
            # Only flag the Fusion.RRF form, not arbitrary user enums named RRF.
            if chain.endswith("Fusion.RRF"):
                offenders.append((file_path, node.lineno, chain))
    return offenders


def _find_custom_rrf_or_boost_fns(
    tree: ast.AST, file_path: Path
) -> list[tuple[Path, int, str]]:
    """Flag function definitions whose name re-implements an SDK primitive."""
    offenders: list[tuple[Path, int, str]] = []
    for fn in _iter_function_defs(tree):
        if fn.name in ALLOWED_FN_NAMES:
            continue
        if any(token in fn.name for token in FORBIDDEN_FN_NAME_TOKENS):
            offenders.append((file_path, fn.lineno, fn.name))
    return offenders


def _find_deprecated_client_search_calls(
    tree: ast.AST, file_path: Path
) -> list[tuple[Path, int, str]]:
    """Flag ``<qdrant-client>.search(...)`` calls — must be ``query_points``.

    Heuristic: the call's receiver chain (e.g. ``self._client``, ``self.client``,
    ``self._qdrant.client``, bare ``client``) contains the token "client".
    Method-named ``search`` on app-level engines (``rrf_engine.search``,
    ``self.search``) is intentionally not flagged — those are not the Qdrant
    SDK entry point.
    """
    offenders: list[tuple[Path, int, str]] = []
    for call in _iter_calls(tree):
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "search"):
            continue
        receiver_src = _attribute_chain(func.value)
        # Only flag when the receiver chain looks like a Qdrant client handle.
        if "client" in receiver_src.lower() or "qdrant" in receiver_src.lower():
            offenders.append((file_path, call.lineno, _attribute_chain(func)))
    return offenders


# ---------------------------------------------------------------------------
# Test entrypoints
# ---------------------------------------------------------------------------


def _load_tree(file_path: Path) -> ast.AST:
    return ast.parse(file_path.read_text(), filename=str(file_path))


def test_audit_files_exist() -> None:
    """Every audit target must exist; otherwise the contract is silently empty."""
    missing = [p for p in SCAN_FILES if not p.exists()]
    assert not missing, (
        "Audit files declared in SCAN_FILES are missing on disk; either restore "
        "them or update SCAN_FILES intentionally:\n"
        + "\n".join(f"  {p.relative_to(REPO_ROOT)}" for p in missing)
    )


def test_no_legacy_fusion_rrf_attribute() -> None:
    """``models.Fusion.RRF`` must not appear — use ``models.RrfQuery(rrf=Rrf(k=...))``."""
    offenders: list[tuple[Path, int, str]] = []
    for path in SCAN_FILES:
        offenders.extend(_find_fusion_rrf_literals(_load_tree(path), path))
    assert not offenders, (
        "Legacy `Fusion.RRF` attribute access found. Replace with the canonical "
        "`models.RrfQuery(rrf=models.Rrf(k=...))` per #1751:\n"
        + "\n".join(
            f"  {p.relative_to(REPO_ROOT)}:{lineno} -> {expr}"
            for p, lineno, expr in offenders
        )
    )


def test_no_custom_rrf_or_score_boost_helpers() -> None:
    """Custom Python rank-fusion / score-boost helpers must not exist."""
    offenders: list[tuple[Path, int, str]] = []
    for path in SCAN_FILES:
        offenders.extend(_find_custom_rrf_or_boost_fns(_load_tree(path), path))
    assert not offenders, (
        "Custom rank-fusion / score-boost helper detected. Use Qdrant SDK "
        "primitives (`RrfQuery`, `FusionQuery`, `FormulaQuery`) instead, or "
        "extend the ALLOWED_FN_NAMES set with a justification:\n"
        + "\n".join(
            f"  {p.relative_to(REPO_ROOT)}:{lineno} -> def {name}(...)"
            for p, lineno, name in offenders
        )
    )


def test_no_deprecated_qdrant_client_search_calls() -> None:
    """Deprecated ``client.search(...)`` is forbidden — use ``client.query_points(...)``."""
    offenders: list[tuple[Path, int, str]] = []
    for path in SCAN_FILES:
        offenders.extend(_find_deprecated_client_search_calls(_load_tree(path), path))
    assert not offenders, (
        "Deprecated `client.search(...)` call detected. Replace with "
        "`client.query_points(...)` (see Qdrant Python client docs):\n"
        + "\n".join(
            f"  {p.relative_to(REPO_ROOT)}:{lineno} -> {expr}(...)"
            for p, lineno, expr in offenders
        )
    )
