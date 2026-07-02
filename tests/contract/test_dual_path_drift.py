"""Drift-guard: both pipeline paths share the same retrieval + generation entrypoints.

Drift risk
----------
The project has two code paths that produce an answer from a user query:

  Core spine (always active):
    src/runtime/pipeline/assistant_pipeline.py
    → rag_pipeline  (src.runtime.pipeline.rag)
    → generate_answer (src.runtime.generation)

  Client-direct fast path (when client_direct_pipeline_enabled):
    telegram_bot/pipelines/client.py
    → rag_pipeline  (src.runtime.pipeline.rag)
    → generate_response (telegram_bot.services.generate_response)
      which delegates to generate_answer (src.runtime.generation)

If a developer rewires the client-direct path to a *different* retrieval or
generation library, the two paths diverge silently and the core Q&A contracts
no longer apply to that code branch.

What this test checks (statically, no imports, no Docker):
  1. Both paths import `rag_pipeline` from `src.runtime.pipeline.rag`.
  2. The core spine imports `generate_answer` from `src.runtime.generation`.
  3. The client-direct path imports `generate_response` from
     `telegram_bot.services.generate_response` (the approved adapter shim).
  4. The generate_response shim itself imports `generate_answer` from
     `src.runtime.generation` — keeping the generation root consistent.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

CORE_SPINE = REPO_ROOT / "src" / "runtime" / "pipeline" / "assistant_pipeline.py"
CLIENT_DIRECT = REPO_ROOT / "telegram_bot" / "pipelines" / "client.py"
GENERATE_RESPONSE_SHIM = REPO_ROOT / "telegram_bot" / "services" / "generate_response.py"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _collect_imports(path: Path) -> list[tuple[str | None, str]]:
    """Return (module, name) pairs for all ImportFrom nodes in *path*.

    Both top-level and deferred (inside function bodies) imports are included
    because the test must catch drift regardless of where the import lives.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: list[tuple[str | None, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                result.append((node.module, alias.name))
    return result


def _imports_name_from_module(path: Path, name: str, module_prefix: str) -> bool:
    """Return True if *path* imports *name* from a module starting with *module_prefix*."""
    for module, imported_name in _collect_imports(path):
        if module is not None and module.startswith(module_prefix) and imported_name == name:
            return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_core_spine_imports_rag_pipeline_from_runtime() -> None:
    """Core spine must import rag_pipeline from src.runtime.pipeline.rag.

    If this fails: assistant_pipeline.py has been rewired to a different
    retrieval implementation. Update both paths or this contract.
    """
    assert _imports_name_from_module(CORE_SPINE, "rag_pipeline", "src.runtime.pipeline.rag"), (
        f"{CORE_SPINE.relative_to(REPO_ROOT)} does not import `rag_pipeline` from "
        "`src.runtime.pipeline.rag`. "
        "The core spine retrieval root has drifted — update or fix both pipeline paths."
    )


def test_client_direct_imports_rag_pipeline_from_runtime() -> None:
    """Client-direct path must import rag_pipeline from src.runtime.pipeline.rag.

    If this fails: telegram_bot/pipelines/client.py has been rewired to a
    different retrieval library. The two paths now diverge on retrieval — the
    core pipeline contracts no longer cover the client-direct path.
    """
    assert _imports_name_from_module(CLIENT_DIRECT, "rag_pipeline", "src.runtime.pipeline.rag"), (
        f"{CLIENT_DIRECT.relative_to(REPO_ROOT)} does not import `rag_pipeline` from "
        "`src.runtime.pipeline.rag`. "
        "Client-direct retrieval has drifted from the canonical RAG pipeline."
    )


def test_core_spine_imports_generate_answer_from_runtime() -> None:
    """Core spine must import generate_answer from src.runtime.generation.

    If this fails: the core generation entrypoint has changed. Check that the
    client-direct path still converges on the same generation root.
    """
    assert _imports_name_from_module(CORE_SPINE, "generate_answer", "src.runtime.generation"), (
        f"{CORE_SPINE.relative_to(REPO_ROOT)} does not import `generate_answer` from "
        "`src.runtime.generation`. "
        "The core spine generation root has drifted."
    )


def test_client_direct_uses_generate_response_shim() -> None:
    """Client-direct path must import generate_response from the approved shim.

    The shim (telegram_bot.services.generate_response) delegates to
    generate_answer from src.runtime.generation. Importing a different
    generation function directly would bypass the canonical generation contract.
    If this fails: client.py has been rewired to call a different generation
    entrypoint. Verify the new entrypoint also delegates to src.runtime.generation.
    """
    assert _imports_name_from_module(
        CLIENT_DIRECT,
        "generate_response",
        "telegram_bot.services.generate_response",
    ), (
        f"{CLIENT_DIRECT.relative_to(REPO_ROOT)} does not import `generate_response` from "
        "`telegram_bot.services.generate_response`. "
        "The client-direct generation path has drifted from the approved shim."
    )


def test_generate_response_shim_delegates_to_runtime_generate_answer() -> None:
    """The generate_response shim must import generate_answer from src.runtime.generation.

    This closes the convergence chain: client-direct → generate_response →
    generate_answer (same root as core spine). If this shim stops delegating
    to src.runtime.generation, the two paths are no longer converged on
    generation.
    """
    assert _imports_name_from_module(
        GENERATE_RESPONSE_SHIM, "generate_answer", "src.runtime.generation"
    ), (
        f"{GENERATE_RESPONSE_SHIM.relative_to(REPO_ROOT)} does not import `generate_answer` "
        "from `src.runtime.generation`. "
        "The generate_response shim no longer delegates to the canonical generation entrypoint."
    )
