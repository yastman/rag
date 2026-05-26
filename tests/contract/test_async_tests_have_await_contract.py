"""Contract: ``async def test_*`` functions must contain at least one ``await`` (#1515 S2).

Background
----------

The audit issue #1515 (Phase 4, smell **S2**) flagged 44 ``async def
test_*`` functions in ``tests/unit/`` whose bodies never use ``await``.
With ``asyncio_mode = "auto"`` configured in ``pyproject.toml`` the tests
still pass — but they confuse new readers ("why is this async?") and
suggest the test exercises an async surface when it does not.

This contract is a **ratchet**:

* ``ALLOWLIST`` records every existing offender at the time #1515 Phase 4
  landed. The list must shrink — never grow — as offenders are migrated
  to plain ``def test_*``.
* New ``async def test_*`` functions that lack ``await`` fail the
  contract immediately, prompting the author to either remove ``async``
  or add the missing ``await``.

The shape mirrors the layering ratchet
(``test_layering_no_telegram_bot_imports_contract.py``) and the chunker
migration ratchet (``test_chunker_migration_1235_contract.py``).
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "tests" / "unit"


# Frozen baseline at the time #1515 Phase 4 landed. Every entry is a
# ``relative/path/to/file.py::test_function_name`` identifier.
# This list MUST shrink as the offenders are migrated to plain
# ``def test_*``. Never regenerate it to silence a failure.
ALLOWLIST: frozenset[str] = frozenset(
    {
        "tests/unit/agents/test_bot_agent_integration.py::test_handle_query_supervisor_imports_available",
        "tests/unit/agents/test_bot_agent_integration.py::test_bot_context_has_required_fields",
        "tests/unit/agents/test_bot_agent_integration.py::test_get_crm_tools_returns_list",
        "tests/unit/agents/test_crm_tools.py::test_get_crm_tools_count",
        "tests/unit/agents/test_history_graph_integration.py::test_graph_compiles",
        "tests/unit/agents/test_nurturing_analytics_tools.py::test_manager_tools_hidden_for_client_role",
        "tests/unit/api/test_rag_api_runtime.py::test_lifespan_respects_rerank_provider_none",
        "tests/unit/api/test_rag_api_runtime.py::test_lifespan_keeps_colbert_runtime_server_side",
        "tests/unit/api/test_rag_api_runtime.py::test_lifespan_unknown_rerank_provider_logs_and_closes_embeddings",
        "tests/unit/contextualization/test_base.py::test_inheritance_preserves_static_methods",
        "tests/unit/dialogs/test_crm_foundation.py::test_kommo_client_has_update_task",
        "tests/unit/dialogs/test_crm_foundation.py::test_kommo_client_has_complete_task",
        "tests/unit/mini_app/test_api_lifespan.py::test_lifespan_opens_and_closes_redis",
        "tests/unit/observability/test_sentry_wiring.py::test_mini_app_lifespan_initializes_sentry_before_redis",
        "tests/unit/services/test_nurturing_scheduler.py::test_scheduler_has_no_jobs_before_start",
        "tests/unit/services/test_rag_core.py::test_all_cacheable_types_are_checked",
        "tests/unit/services/test_session_summary_worker.py::test_cap_default_is_50",
        "tests/unit/services/test_session_summary_worker.py::test_cap_clamps_at_minimum_one",
        "tests/unit/test_agent_streaming.py::test_stream_agent_to_draft_is_importable",
        "tests/unit/test_bot_handlers.py::test_no_handle_promotions_method",
        "tests/unit/test_perf_fixes.py::test_start_calls_warmup_bge",
        "tests/unit/test_preflight.py::test_postgres_in_dep_classification_as_optional",
        "tests/unit/test_topic_service_init.py::test_bot_has_topic_service_attr",
    }
)


def _collect_offenders() -> set[str]:
    """Return the set of ``relative_path::function_name`` for every async test
    under ``tests/unit/`` whose body does not contain ``await``.
    """
    offenders: set[str] = set()
    if not SCAN_ROOT.exists():
        return offenders

    for path in sorted(SCAN_ROOT.rglob("*.py")):
        if "/.venv/" in str(path) or "/__pycache__/" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            has_await = any(isinstance(child, ast.Await) for child in ast.walk(node))
            if not has_await:
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.add(f"{rel}::{node.name}")
    return offenders


def test_no_new_async_tests_without_await() -> None:
    """New ``async def test_*`` functions must contain at least one ``await``.

    Either drop ``async`` (the test is sync) or add the missing ``await``.
    """
    offenders = _collect_offenders()
    new_offenders = sorted(offenders - ALLOWLIST)
    assert not new_offenders, (
        "#1515 S2: new async test(s) without `await` detected. "
        "Convert to a plain `def test_*` if the body is sync, or add the "
        "missing `await` if it should genuinely exercise async code.\n"
        "New offenders:\n  - " + "\n  - ".join(new_offenders)
    )


def test_async_test_allowlist_does_not_grow_stale() -> None:
    """Allowlist entries must still match real offenders.

    When a contributor migrates an entry to a plain ``def test_*``, the
    allowlist must be shrunk at the same time. This test catches the
    half-done case where the test name was renamed or moved but the
    allowlist still references the old identifier.
    """
    offenders = _collect_offenders()
    stale = sorted(ALLOWLIST - offenders)
    assert not stale, (
        "#1515 S2: allowlist entries no longer match real offenders. "
        "Either restore the offending test or remove the stale entry from "
        "ALLOWLIST in this contract:\n  - " + "\n  - ".join(stale)
    )
