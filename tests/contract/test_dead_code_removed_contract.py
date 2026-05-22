"""Contract test for issue #1541: confirmed dead-code removals must stay gone.

This file is the forward-looking guardrail for the safe slice of the #1541
dead-code cleanup. Each parametrised case asserts that a specific symbol or
construct does NOT exist in the live source tree.

Items removed in PR #1843 (initial slice):

* ``QdrantService.mmr_rerank`` — never called outside its own tests
  (``telegram_bot/services/qdrant.py``).
* ``_PROPERTY_TYPE_QUERY_TEXT`` — module-level dict in
  ``telegram_bot/dialogs/funnel.py`` with zero references.
* ``_remove_reply_keyboard`` — async helper in
  ``telegram_bot/dialogs/catalog.py`` with zero callers.
* ``BGEM3Client.health`` — method with zero non-test callers in
  ``telegram_bot/services/bge_m3_client.py`` (preflight uses a raw HTTP
  ``GET /health`` against ``client._client``, not this method).

Items removed in this PR (residual #1541 slice):

* Item #1 ``telegram_bot/services/llm.py`` (whole file, 381 lines) — only
  importer is its own test suite (``tests/unit/services/test_llm.py``,
  ``tests/unit/services/test_llm_observability.py``,
  ``tests/unit/test_guardrails.py``, ``tests/integration/test_llm_generate.py``,
  ``tests/chaos/test_llm_fallback.py``) and the lazy-export map in
  ``telegram_bot/services/__init__.py``. Production code uses
  ``generate_response.py`` instead.
* Item #3 ``QdrantService.search_with_score_boosting`` (~150 lines) — large
  block; no production callers, only own tests.
* Item #6 Kommo task creation in ``utility_tools.handoff`` — branch is
  guarded by ``lead_id`` which is always ``None``, so the branch is
  unreachable. Removed together with the now-orphaned ``elif kommo`` log
  branch and ``TaskCreate`` import.

Items still NOT in scope:

* Item #7 ``KommoClient.update_lead_score`` — actually live: called from
  ``telegram_bot/services/lead_score_sync.py:64``. Not dead.
* Item #10 ``_BACKGROUND_TASKS`` set in ``funnel.py`` — Python's asyncio
  documentation explicitly recommends keeping a strong reference to the
  result of ``asyncio.create_task`` to prevent garbage collection. Removing
  this set would risk regressing the very GC-prevention pattern it
  implements.

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
    tree = _parse("src/services/bge_m3_client.py")
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
        # search_with_score_boosting — same pattern; tests target the now
        # removed method exclusively.
        ("tests/unit/test_qdrant_service.py", "TestQdrantServiceScoreBoosting"),
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


# ---------------------------------------------------------------------------
# 5. services/llm.py — whole file removal (#1541 item #1).
# ---------------------------------------------------------------------------


def test_services_llm_module_is_gone() -> None:
    """``telegram_bot/services/llm.py`` must be deleted (#1541 item #1).

    Production code uses ``telegram_bot.services.generate_response`` instead.
    The previous file was deprecated in #1671's wake and only its own tests
    plus the lazy-export map kept it alive.
    """
    src_path = REPO_ROOT / "telegram_bot" / "services" / "llm.py"
    assert not src_path.is_file(), (
        "telegram_bot/services/llm.py was removed in #1541 (residual slice)."
        " Re-introducing it requires deleting this contract assertion and"
        " documenting the new use case + migration plan."
    )


def test_services_init_drops_llm_lazy_exports() -> None:
    """``services/__init__.py`` must not lazy-export anything from ``.llm``."""
    init_text = (REPO_ROOT / "telegram_bot" / "services" / "__init__.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("LLMService", "LOW_CONFIDENCE_THRESHOLD", "ConfidenceResult")
    for symbol in forbidden:
        # Dotted import target like '"LLMService": ".llm"'
        assert f'"{symbol}": ".llm"' not in init_text, (
            f"telegram_bot/services/__init__.py still lazy-imports {symbol} from .llm;"
            " remove the entry now that services/llm.py is deleted."
        )
        # Top-level reference like 'from .llm import LLMService'
        assert "from .llm import" not in init_text, (
            "services/__init__.py must not do `from .llm import ...` after #1541 residual."
        )


def test_llm_observability_yaml_drops_llm_service_spans() -> None:
    """``trace_contract.yaml`` must not list any ``llm-service-*`` span entry."""
    yaml_path = REPO_ROOT / "tests" / "observability" / "trace_contract.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    for span in (
        "llm-service-generate",
        "llm-service-generate-answer",
        "llm-service-stream-answer",
    ):
        assert f"- {span}" not in yaml_text, (
            f"{span} entry must be removed from trace_contract.yaml after services/llm.py"
            " deletion (no source emits it any more)."
        )


def test_error_contract_drops_services_llm_allowlist() -> None:
    """``ERROR_SPAN_ALLOWLIST`` must not allowlist ``services/llm.py`` any more."""
    err_path = REPO_ROOT / "tests" / "contract" / "test_error_contract.py"
    err_text = err_path.read_text(encoding="utf-8")
    assert '"telegram_bot/services/llm.py"' not in err_text, (
        "tests/contract/test_error_contract.py still lists services/llm.py in"
        " ERROR_SPAN_ALLOWLIST; remove the entry now that the module is deleted."
    )


# ---------------------------------------------------------------------------
# 6. QdrantService.search_with_score_boosting (#1541 item #3).
# ---------------------------------------------------------------------------


def test_qdrant_service_search_with_score_boosting_method_is_gone() -> None:
    """``QdrantService.search_with_score_boosting`` must be removed (#1541 item #3)."""
    tree = _parse("telegram_bot/services/qdrant.py")
    qdrant_class: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "QdrantService":
            qdrant_class = node
            break
    assert qdrant_class is not None, "QdrantService class must exist in qdrant.py"
    assert not _has_function(qdrant_class, "search_with_score_boosting"), (
        "QdrantService.search_with_score_boosting was removed in #1541 (no production"
        " callers, only its own tests). Re-introducing it requires updating this"
        " contract test and wiring the method into the production retrieval path."
    )


def test_qdrant_score_boosting_yaml_span_is_gone() -> None:
    """``trace_contract.yaml`` must not list ``qdrant-search-score-boosting``."""
    yaml_path = REPO_ROOT / "tests" / "observability" / "trace_contract.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    assert "- qdrant-search-score-boosting" not in yaml_text, (
        "qdrant-search-score-boosting entry must be removed from trace_contract.yaml"
        " after the QdrantService method is deleted."
    )


def test_span_coverage_contract_drops_score_boosting() -> None:
    """``RETRIEVER_SPANS`` in span_coverage_contract.py must not list it any more."""
    contract_path = REPO_ROOT / "tests" / "contract" / "test_span_coverage_contract.py"
    contract_text = contract_path.read_text(encoding="utf-8")
    assert '"qdrant-search-score-boosting"' not in contract_text, (
        "tests/contract/test_span_coverage_contract.py still lists"
        " qdrant-search-score-boosting in RETRIEVER_SPANS; remove the entry."
    )


# ---------------------------------------------------------------------------
# 7. utility_tools.handoff — Kommo task creation branch (#1541 item #6).
# ---------------------------------------------------------------------------


def test_handoff_drops_kommo_task_creation_branch() -> None:
    """``utility_tools.handoff`` must not call ``kommo.create_task`` any more.

    The previous branch was guarded by ``lead_id`` which was always ``None``,
    so the call was unreachable. Removing it lets the function shed its
    ``TaskCreate`` import and the orphaned ``elif kommo`` log branch.
    """
    tree = _parse("telegram_bot/agents/utility_tools.py")
    handoff_func: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handoff":
            handoff_func = node
            break
    assert handoff_func is not None, "handoff async function must exist in utility_tools.py"

    # Walk every Call inside handoff and forbid kommo.create_task / TaskCreate.
    for sub in ast.walk(handoff_func):
        if not isinstance(sub, ast.Call):
            continue
        target = sub.func
        if isinstance(target, ast.Attribute) and target.attr == "create_task":
            value = target.value
            if isinstance(value, ast.Name) and value.id == "kommo":
                pytest.fail(
                    "handoff must not call kommo.create_task; the lead_id resolution"
                    " path was never implemented and the branch was unreachable."
                )
        if isinstance(target, ast.Name) and target.id == "TaskCreate":
            pytest.fail(
                "handoff must not construct TaskCreate; the Kommo handoff task"
                " creation branch was removed in #1541 (residual slice)."
            )


def test_handoff_drops_lead_id_resolution_placeholder() -> None:
    """The placeholder ``lead_id: int | None = None`` must be gone with the branch."""
    src_text = (REPO_ROOT / "telegram_bot" / "agents" / "utility_tools.py").read_text(
        encoding="utf-8"
    )
    assert "lead_id: int | None = None" not in src_text, (
        "The lead_id placeholder annotation must be removed alongside the dead Kommo"
        " task-creation branch in handoff (#1541 item #6)."
    )
