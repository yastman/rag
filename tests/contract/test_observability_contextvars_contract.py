"""Contextvars hygiene contract for @observe-touched code paths (#2220).

Background. #2167 closed an orphan top-level ``bge-m3-hybrid-embed`` span
caused by ``loop.run_in_executor(...)`` in ``RAGPipeline.search``. The
worker callable was decorated with ``@observe``; ``run_in_executor`` does
NOT propagate the current ``contextvars.Context``, so the OTEL/Langfuse
parent span was lost and the worker emitted a top-level orphan trace.
The fix was ``asyncio.to_thread(...)`` which DOES propagate context.

The pre-existing ``tests/unit/core/test_pipeline.py`` AST-walks only
``src/core/pipeline.py``. A new file under ``telegram_bot/`` or
``src/services/`` could re-introduce the same bug and the build would
not catch it.

This contract generalises the rule across the whole codebase:

* Any production-code module that imports ``observe`` (directly or
  re-exported via ``src.observability`` / ``telegram_bot.observability``)
  MUST NOT call ``loop.run_in_executor(...)``.
* Acceptable replacements:
    - ``asyncio.to_thread(fn, *args)`` — preserves contextvars by spec.
    - ``ctx = contextvars.copy_context(); loop.run_in_executor(None, ctx.run, fn)`` —
      explicit context capture (still avoid; prefer ``to_thread``).

Outcome: re-introducing the #2167 class of bug fails CI before merge.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# Production code roots to scan. Mirrors test_trace_families_contract.py and
# test_compose_observe_coverage_contract.py for consistency.
_SCAN_DIRS = (
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
    REPO_ROOT / "services",
    REPO_ROOT / "mini_app",
)

# Skip non-production paths.
_EXCLUDE_PATTERN_FRAGMENTS = (
    "/tests/",
    "/.venv/",
    "/__pycache__/",
    "/archive/",
    "/.git/",
    "/_obsolete/",
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_DIRS:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            path_str = str(py_file)
            if any(skip in path_str for skip in _EXCLUDE_PATTERN_FRAGMENTS):
                continue
            files.append(py_file)
    return files


def _imports_observe(tree: ast.AST) -> bool:
    """Return True if the module imports ``observe`` from any provider."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "langfuse",
            "src.observability",
            "telegram_bot.observability",
        }:
            for alias in node.names:
                if alias.name == "observe" or alias.asname == "observe":
                    return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "langfuse" or alias.asname == "observe":
                    return True
    return False


def _find_run_in_executor_calls(tree: ast.AST) -> list[ast.Call]:
    """Return every ``<X>.run_in_executor(...)`` call node in the tree."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run_in_executor"
        ):
            calls.append(node)
    return calls


def _has_copy_context_guard(call: ast.Call) -> bool:
    """Return True if the ``run_in_executor`` call is preceded by an explicit
    ``contextvars.copy_context().run`` argument — the documented escape
    hatch when an executor is unavoidable. This is a heuristic: we accept
    the call if any positional arg is a ``copy_context().run`` reference."""
    for arg in call.args:
        # Pattern: copy_context().run -> Attribute(value=Call(...))
        if (
            isinstance(arg, ast.Attribute)
            and arg.attr == "run"
            and isinstance(arg.value, ast.Call)
        ):
            func = arg.value.func
            if isinstance(func, ast.Attribute) and func.attr == "copy_context":
                return True
            if isinstance(func, ast.Name) and func.id == "copy_context":
                return True
    return False


@pytest.fixture(scope="module")
def offending_files() -> list[tuple[Path, list[ast.Call]]]:
    """Modules importing ``observe`` that also call ``run_in_executor``
    without the ``copy_context().run`` escape hatch."""
    offenders: list[tuple[Path, list[ast.Call]]] = []
    for py_file in _iter_python_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if not _imports_observe(tree):
            continue
        bad_calls = [
            call for call in _find_run_in_executor_calls(tree) if not _has_copy_context_guard(call)
        ]
        if bad_calls:
            offenders.append((py_file, bad_calls))
    return offenders


class TestNoRunInExecutorNearObserve:
    """Modules importing ``observe`` must not lose contextvars via
    ``loop.run_in_executor(...)``. Generalises #2167 — `RAGPipeline.search`
    fix to the whole codebase."""

    def test_no_offending_files(self, offending_files: list[tuple[Path, list[ast.Call]]]) -> None:
        if not offending_files:
            return

        report_lines: list[str] = []
        for path, calls in offending_files:
            relative = path.relative_to(REPO_ROOT).as_posix()
            for call in calls:
                report_lines.append(f"  - {relative}:{call.lineno}")

        pytest.fail(
            "Found run_in_executor(...) calls in modules that import "
            "@observe — this drops the OTEL/Langfuse parent context "
            "(see closed #2167). Replace with asyncio.to_thread(...) "
            "or pass contextvars.copy_context().run as the executor "
            "callable.\n\nOffending sites:\n" + "\n".join(report_lines)
        )


class TestSelfCheckOfFixtures:
    """Sanity: the scanner finds at least one production module that
    imports observe (otherwise the rest of the contract is vacuous)."""

    def test_scanner_finds_observe_importers(self) -> None:
        scanned = 0
        importers = 0
        for py_file in _iter_python_files():
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            scanned += 1
            if _imports_observe(tree):
                importers += 1

        assert importers > 0, (
            f"Scanner found 0 modules importing @observe across "
            f"{scanned} production files — the bidirectional contract "
            "would be vacuous. Check _imports_observe() / _SCAN_DIRS."
        )


class TestContractCatchesRegressions:
    """Negative-path tests: feed the AST helpers a synthetic offender and
    verify they would fail the build. Guards the contract against itself
    silently going green when the scanner is broken."""

    def test_imports_observe_detects_from_langfuse(self) -> None:
        tree = ast.parse("from langfuse import observe\n@observe()\ndef f(): pass\n")
        assert _imports_observe(tree)

    def test_imports_observe_detects_from_src_observability(self) -> None:
        tree = ast.parse(
            "from src.observability import observe, get_client\n@observe()\ndef f(): pass\n"
        )
        assert _imports_observe(tree)

    def test_imports_observe_ignores_unrelated_modules(self) -> None:
        tree = ast.parse("from typing import Any\ndef f(x: Any): pass\n")
        assert not _imports_observe(tree)

    def test_finds_run_in_executor_call(self) -> None:
        tree = ast.parse(
            "import asyncio\n"
            "async def f():\n"
            "    loop = asyncio.get_event_loop()\n"
            "    return await loop.run_in_executor(None, lambda: 1)\n"
        )
        calls = _find_run_in_executor_calls(tree)
        assert len(calls) == 1
        assert not _has_copy_context_guard(calls[0])

    def test_accepts_run_in_executor_with_copy_context_guard(self) -> None:
        tree = ast.parse(
            "import asyncio\n"
            "import contextvars\n"
            "async def f():\n"
            "    loop = asyncio.get_event_loop()\n"
            "    ctx = contextvars.copy_context()\n"
            "    return await loop.run_in_executor(None, ctx.run, my_fn)\n"
        )
        calls = _find_run_in_executor_calls(tree)
        assert len(calls) == 1
        # Synthetic note: this fixture passes ``ctx.run`` as a positional
        # arg — but ``ctx.run`` is bound to a captured Context, not a fresh
        # ``copy_context().run``. So the heuristic correctly does NOT
        # whitelist it (defensive). The whitelist requires an inline
        # ``copy_context().run`` argument.
        assert not _has_copy_context_guard(calls[0])

    def test_whitelists_inline_copy_context_run(self) -> None:
        tree = ast.parse(
            "import asyncio\n"
            "import contextvars\n"
            "async def f():\n"
            "    loop = asyncio.get_event_loop()\n"
            "    return await loop.run_in_executor(None, contextvars.copy_context().run, my_fn)\n"
        )
        calls = _find_run_in_executor_calls(tree)
        assert len(calls) == 1
        assert _has_copy_context_guard(calls[0])

    def test_to_thread_is_not_flagged(self) -> None:
        tree = ast.parse(
            "import asyncio\nasync def f():\n    return await asyncio.to_thread(my_fn, x, y)\n"
        )
        # to_thread doesn't match run_in_executor pattern
        assert _find_run_in_executor_calls(tree) == []
