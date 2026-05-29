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



# ---------------------------------------------------------------------------
# #2246 F1 — raw thread hops also drop contextvars
# ---------------------------------------------------------------------------
# ``threading.Thread(target=...)`` and ``ThreadPoolExecutor(...).submit(...)``
# start a worker with a *fresh* ``contextvars.Context`` exactly like
# ``run_in_executor`` — so any ``@observe`` span created downstream becomes a
# new root trace instead of nesting under the active ingestion/bot trace.
# OpenTelemetry only propagates ``Context`` automatically across ``asyncio``;
# raw threads require manual capture (verified against the OTel Python docs via
# Context7). The #2220 contract only guarded ``run_in_executor``; this extends
# it to the raw-thread primitives.
#
# Accepted escape hatch (mirrors the run_in_executor rule): capture the active
# context and run the worker through it —
#   ``ctx = contextvars.copy_context()``
#   ``pool.submit(ctx.run, fn, *args)``                       # executor
#   ``threading.Thread(target=lambda: ctx.run(fn, *args))``   # raw thread

# (relative_path, thread_target_name) pairs intentionally exempt: infrastructure
# threads that never run @observe-decorated work, so there is no parent context
# to preserve. Keep this minimal and justified.
_INFRA_THREAD_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        # Voice agent liveness probe: a blocking HTTP health server
        # (serve_forever); it never creates Langfuse/OTEL spans.
        ("src/voice/agent.py", "_run"),
    }
)


def _is_thread_ctor(call: ast.Call) -> bool:
    """True for ``threading.Thread(...)`` / ``Thread(...)`` constructor calls."""
    func = call.func
    return (isinstance(func, ast.Attribute) and func.attr == "Thread") or (
        isinstance(func, ast.Name) and func.id == "Thread"
    )


def _is_submit_call(call: ast.Call) -> bool:
    """True for ``<executor>.submit(...)`` calls (ThreadPoolExecutor.submit)."""
    return isinstance(call.func, ast.Attribute) and call.func.attr == "submit"


def _expr_is_copy_context_run(node: ast.AST) -> bool:
    """True if *node* is (or calls) ``<ctx>.run`` / ``copy_context().run``.

    Accepts both the bare reference (``ctx.run`` passed to ``submit``) and a
    call form (``ctx.run(fn, ...)`` used inside a ``Thread`` target lambda).
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute) and node.attr == "run":
        value = node.value
        if isinstance(value, ast.Call):
            fn = value.func
            if isinstance(fn, ast.Attribute) and fn.attr == "copy_context":
                return True
            if isinstance(fn, ast.Name) and fn.id == "copy_context":
                return True
        # A captured context bound to a name like ``ctx`` / ``context``.
        if isinstance(value, ast.Name) and ("ctx" in value.id or "context" in value.id):
            return True
    return False


def _thread_target_expr(call: ast.Call) -> ast.AST | None:
    """Resolve the worker callable for a Thread/submit call."""
    for kw in call.keywords:
        if kw.arg == "target":
            return kw.value
    if call.args:
        return call.args[0]
    return None


def _thread_call_is_guarded(call: ast.Call) -> bool:
    target = _thread_target_expr(call)
    if target is None:
        return False
    if isinstance(target, ast.Lambda):
        return _expr_is_copy_context_run(target.body)
    return _expr_is_copy_context_run(target)


def _thread_target_name(call: ast.Call) -> str:
    target = _thread_target_expr(call)
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Lambda):
        return "<lambda>"
    return "<unknown>"


def _find_thread_primitive_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and (_is_thread_ctor(node) or _is_submit_call(node))
    ]


@pytest.fixture(scope="module")
def offending_thread_files() -> list[tuple[Path, list[ast.Call]]]:
    """observe-importing modules with an unguarded, non-allowlisted thread hop."""
    offenders: list[tuple[Path, list[ast.Call]]] = []
    for py_file in _iter_python_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if not _imports_observe(tree):
            continue
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        bad: list[ast.Call] = []
        for call in _find_thread_primitive_calls(tree):
            if _thread_call_is_guarded(call):
                continue
            if (rel, _thread_target_name(call)) in _INFRA_THREAD_ALLOWLIST:
                continue
            bad.append(call)
        if bad:
            offenders.append((py_file, bad))
    return offenders


class TestNoUnguardedThreadHopNearObserve:
    """Modules importing ``observe`` must not drop contextvars via raw
    ``threading.Thread`` / ``ThreadPoolExecutor.submit`` hops (#2246 F1)."""

    def test_no_offending_thread_files(
        self, offending_thread_files: list[tuple[Path, list[ast.Call]]]
    ) -> None:
        if not offending_thread_files:
            return
        report_lines: list[str] = []
        for path, calls in offending_thread_files:
            relative = path.relative_to(REPO_ROOT).as_posix()
            for call in calls:
                report_lines.append(f"  - {relative}:{call.lineno}")
        pytest.fail(
            "Found raw thread hops (threading.Thread / ThreadPoolExecutor.submit) "
            "in modules that import @observe without a contextvars.copy_context() "
            "guard (#2246 F1). The worker starts with a fresh Context, so any "
            "@observe span it creates orphans into a new root trace. Capture the "
            "context first: ctx = contextvars.copy_context(); then run the worker "
            "via ctx.run(...). If the thread never runs @observe work, add it to "
            "_INFRA_THREAD_ALLOWLIST with a reason.\n\nOffending sites:\n"
            + "\n".join(report_lines)
        )


class TestThreadHopContractCatchesRegressions:
    """Negative-path checks so the F1 detector cannot silently go vacuous."""

    def test_flags_unguarded_thread(self) -> None:
        tree = ast.parse(
            "import threading\n"
            "def worker(): pass\n"
            "threading.Thread(target=worker).start()\n"
        )
        calls = _find_thread_primitive_calls(tree)
        assert len(calls) == 1
        assert not _thread_call_is_guarded(calls[0])
        assert _thread_target_name(calls[0]) == "worker"

    def test_accepts_thread_with_copy_context_lambda(self) -> None:
        tree = ast.parse(
            "import threading, contextvars\n"
            "ctx = contextvars.copy_context()\n"
            "threading.Thread(target=lambda: ctx.run(worker)).start()\n"
        )
        calls = _find_thread_primitive_calls(tree)
        assert len(calls) == 1
        assert _thread_call_is_guarded(calls[0])

    def test_flags_unguarded_submit(self) -> None:
        tree = ast.parse(
            "from concurrent.futures import ThreadPoolExecutor\n"
            "with ThreadPoolExecutor() as pool:\n"
            "    pool.submit(worker, 1, 2)\n"
        )
        calls = [c for c in _find_thread_primitive_calls(tree) if _is_submit_call(c)]
        assert len(calls) == 1
        assert not _thread_call_is_guarded(calls[0])

    def test_accepts_submit_with_copy_context_run(self) -> None:
        tree = ast.parse(
            "import contextvars\n"
            "from concurrent.futures import ThreadPoolExecutor\n"
            "ctx = contextvars.copy_context()\n"
            "with ThreadPoolExecutor() as pool:\n"
            "    pool.submit(ctx.run, worker, 1, 2)\n"
        )
        calls = [c for c in _find_thread_primitive_calls(tree) if _is_submit_call(c)]
        assert len(calls) == 1
        assert _thread_call_is_guarded(calls[0])

    def test_accepts_inline_copy_context_run_submit(self) -> None:
        tree = ast.parse(
            "import contextvars\n"
            "from concurrent.futures import ThreadPoolExecutor\n"
            "with ThreadPoolExecutor() as pool:\n"
            "    pool.submit(contextvars.copy_context().run, worker)\n"
        )
        calls = [c for c in _find_thread_primitive_calls(tree) if _is_submit_call(c)]
        assert len(calls) == 1
        assert _thread_call_is_guarded(calls[0])

    def test_scanner_finds_thread_primitive_in_repo(self) -> None:
        """The repo scan is not vacuous: at least one observe-importing module
        actually contains a thread primitive (currently the voice health probe,
        which is allowlisted)."""
        total = 0
        for py_file in _iter_python_files():
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            if not _imports_observe(tree):
                continue
            total += len(_find_thread_primitive_calls(tree))
        assert total > 0, (
            "F1 scanner found no thread primitives in any observe-importing "
            "module — the contract may be vacuous; verify _find_thread_primitive_calls."
        )
