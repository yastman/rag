"""Contract test for issue #1541: confirmed dead-code removals must stay gone.

This file is the forward-looking guardrail for the safe slice of the #1541
dead-code cleanup. Each parametrised case asserts that a specific symbol or
construct does NOT exist in the live source tree.

Safe-slice items removed in PR #1541 (this PR):

* ``QdrantService.mmr_rerank`` — never called outside its own tests
  (``telegram_bot/services/qdrant.py``).
* ``_PROPERTY_TYPE_QUERY_TEXT`` — module-level dict in
  ``telegram_bot/dialogs/funnel.py`` with zero references.
* ``_remove_reply_keyboard`` — async helper in
  ``telegram_bot/dialogs/catalog.py`` with zero callers.
* ``BGEM3Client.health`` — method with zero non-test callers in
  ``telegram_bot/services/bge_m3_client.py`` (preflight uses a raw HTTP
  ``GET /health`` against ``client._client``, not this method).

Items DEFERRED to follow-up PRs (still on the #1541 list, kept for clarity):

* Item #1 ``telegram_bot/services/llm.py`` (whole file, 381 lines) —
  re-exported via ``telegram_bot/services/__init__.py`` (``LLMService``,
  ``LOW_CONFIDENCE_THRESHOLD``, ``ConfidenceResult``) and imported by three
  test modules (``test_llm.py``, ``test_llm_observability.py``,
  ``test_guardrails.py``). Not yet a no-op to delete.
* Item #3 ``QdrantService.search_with_score_boosting`` (152 lines) — large
  block; no production callers, only own tests. Defer per issue's
  "probably risky" guidance.
* Item #6 Kommo task creation in ``utility_tools.handoff`` — branch is
  guarded by ``lead_id`` which is always ``None``, so the branch is dead,
  but removal is a behavioural simplification rather than pure dead-code
  cleanup. Defer.
* Item #7 ``KommoClient.update_lead_score`` — actually live: called from
  ``telegram_bot/services/lead_score_sync.py:64``. Not dead.
* Item #10 ``_BACKGROUND_TASKS`` set in ``funnel.py`` — Python's asyncio
  documentation explicitly recommends keeping a strong reference to the
  result of ``asyncio.create_task`` to prevent garbage collection. Removing
  this set would risk regressing the very GC-prevention pattern it
  implements. Defer.

Already removed on ``dev`` independently of this PR:

* Item #2 ``DraftStreamer`` — gone since #1671; see existing
  ``tests/unit/services/test_draft_streamer_removed.py`` for the lock.

Refs #1541.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse(rel_path: str) -> ast.Module:
    """Parse a source file as an AST module."""
    src_path = REPO_ROOT / rel_path
    assert src_path.is_file(), f"expected source file to exist: {src_path}"
    return ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))


def _has_function(tree: ast.AST, name: str) -> bool:
    """Return True if a top-level or nested function/method ``name`` exists."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
    return False


def _has_assignment(tree: ast.AST, name: str) -> bool:
    """Return True if a module-level assignment to ``name`` exists.

    Handles both plain ``Assign`` (``X = ...``) and ``AnnAssign``
    (``X: T = ...``) at module scope.
    """
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return True
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                return True
    return False


# ---------------------------------------------------------------------------
# 1. QdrantService.mmr_rerank — method must not exist on the class.
# ---------------------------------------------------------------------------


def test_qdrant_service_mmr_rerank_method_is_gone() -> None:
    """``QdrantService.mmr_rerank`` must be removed (#1541 item #4)."""
    tree = _parse("telegram_bot/services/qdrant.py")
    qdrant_class: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "QdrantService":
            qdrant_class = node
            break
    assert qdrant_class is not None, "QdrantService class must exist in qdrant.py"
    assert not _has_function(qdrant_class, "mmr_rerank"), (
        "QdrantService.mmr_rerank was removed in #1541 (had no production callers)."
        " Re-introducing it requires updating this contract test and documenting"
        " the new use case."
    )


# ---------------------------------------------------------------------------
# 2. _PROPERTY_TYPE_QUERY_TEXT — module-level dict in funnel.py.
# ---------------------------------------------------------------------------


def test_funnel_property_type_query_text_dict_is_gone() -> None:
    """``_PROPERTY_TYPE_QUERY_TEXT`` must be removed from funnel.py (#1541 item #5)."""
    tree = _parse("telegram_bot/dialogs/funnel.py")
    assert not _has_assignment(tree, "_PROPERTY_TYPE_QUERY_TEXT"), (
        "_PROPERTY_TYPE_QUERY_TEXT was removed in #1541 (zero references)."
    )


# ---------------------------------------------------------------------------
# 3. _remove_reply_keyboard — async helper in catalog.py.
# ---------------------------------------------------------------------------


def test_catalog_remove_reply_keyboard_helper_is_gone() -> None:
    """``_remove_reply_keyboard`` must be removed from catalog.py (#1541 item #8)."""
    tree = _parse("telegram_bot/dialogs/catalog.py")
    assert not _has_function(tree, "_remove_reply_keyboard"), (
        "_remove_reply_keyboard was removed in #1541 (zero callers)."
    )


# ---------------------------------------------------------------------------
# 4. BGEM3Client.health — method on the BGE-M3 client.
# ---------------------------------------------------------------------------


def test_bge_m3_client_health_method_is_gone() -> None:
    """``BGEM3Client.health`` must be removed (#1541 item #9).

    The preflight check uses a raw ``client._client.get(...)`` against the
    ``/health`` endpoint, not this convenience wrapper, so removing the
    method does not regress runtime behaviour.
    """
    tree = _parse("telegram_bot/services/bge_m3_client.py")
    bge_class: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "BGEM3Client":
            bge_class = node
            break
    assert bge_class is not None, "BGEM3Client class must exist in bge_m3_client.py"
    assert not _has_function(bge_class, "health"), (
        "BGEM3Client.health was removed in #1541 (no non-test callers)."
    )


# ---------------------------------------------------------------------------
# Cross-cutting: any unit test that ONLY exercises the removed methods must
# also be gone, otherwise pytest will fail with ImportError / AttributeError.
# ---------------------------------------------------------------------------

_REMOVED_TEST_CLASSES = pytest.mark.parametrize(
    ("rel_path", "class_name"),
    [
        # mmr_rerank — both unit and integration test classes were exclusive
        # to the removed method.
        ("tests/unit/test_qdrant_service.py", "TestQdrantServiceMMR"),
        ("tests/integration/test_qdrant_service.py", "TestMMRRerank"),
    ],
)


@_REMOVED_TEST_CLASSES
def test_dead_code_test_classes_are_gone(rel_path: str, class_name: str) -> None:
    """Dead-code-only test classes must be deleted alongside the production code."""
    src_path = REPO_ROOT / rel_path
    if not src_path.is_file():
        # The whole test file may have been deleted (e.g. when every test in
        # the file targeted dead code). That is acceptable.
        return
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            pytest.fail(
                f"{class_name} in {rel_path} should have been removed alongside its"
                " production target."
            )
