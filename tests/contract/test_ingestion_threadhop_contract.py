"""Ingestion raw-thread-hop context-propagation contract (#2251).

Background. The Phase-2 contextvars contract (#2220,
``test_observability_contextvars_contract.py``) guards
``loop.run_in_executor(...)`` near ``@observe``. But the ingestion path
crosses thread boundaries with *other* raw primitives that the #2220
scanner does not cover:

* ``concurrent.futures.ThreadPoolExecutor().submit(asyncio.run, coro)``
* ``threading.Thread(target=_runner)`` where ``_runner`` calls ``asyncio.run(...)``
* ``threading.Thread(target=lambda: asyncio.run(...))``

A raw thread starts with a clean ``contextvars.Context`` and
``asyncio.run`` spins a *fresh* event loop, so the active OTEL/Langfuse
parent span is lost. Downstream ``@observe`` spans
(``ingestion-flow-run-once``, ``ingestion-indexer-embed-texts``,
``ingestion-qdrant-upsert-chunks``, ...) then become orphan root traces
instead of nesting under ``ingestion-cli-run``.

Per the OpenTelemetry Python docs, asyncio propagates ``Context``
automatically but **threads must propagate it manually**. The documented
Pythonic escape hatch is ``contextvars.copy_context().run(...)``: capture
the active context on the parent thread and re-activate it inside the
worker so child spans (and the Task created by ``asyncio.run``) inherit
the parent. Content was rephrased for compliance with licensing
restrictions.

Contract. Any module under ``src/ingestion`` that BOTH spawns a raw
thread (``threading.Thread(...)`` or ``<executor>.submit(...)``) AND
starts a fresh event loop (``asyncio.run(...)``) MUST also use
``contextvars.copy_context`` to propagate context into that thread.

Outcome: re-introducing the orphan-trace class of bug in the ingestion
path fails CI before merge.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_DIR = REPO_ROOT / "src" / "ingestion"

_EXCLUDE_PATTERN_FRAGMENTS = (
    "/tests/",
    "/.venv/",
    "/__pycache__/",
    "/archive/",
    "/.git/",
    "/_obsolete/",
)


def _iter_ingestion_files() -> list[Path]:
    files: list[Path] = []
    if not INGESTION_DIR.exists():
        return files
    for py_file in INGESTION_DIR.rglob("*.py"):
        if any(skip in str(py_file) for skip in _EXCLUDE_PATTERN_FRAGMENTS):
            continue
        files.append(py_file)
    return files


def _spawns_raw_thread(tree: ast.AST) -> bool:
    """True if the module constructs a ``threading.Thread`` or calls
    ``<executor>.submit(...)`` — i.e. hands work to a raw thread that does
    NOT inherit the current ``contextvars.Context``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # threading.Thread(...) / Thread(...)
        if isinstance(func, ast.Attribute) and func.attr == "Thread":
            return True
        if isinstance(func, ast.Name) and func.id == "Thread":
            return True
        # <executor>.submit(...)
        if isinstance(func, ast.Attribute) and func.attr == "submit":
            return True
    return False


def _starts_fresh_event_loop(tree: ast.AST) -> bool:
    """True if the module calls ``asyncio.run(...)`` (or references it) —
    the signal that a brand-new event loop is created inside the hop."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "run"
            and isinstance(node.value, ast.Name)
            and node.value.id == "asyncio"
        ):
            return True
    return False


def _uses_copy_context(tree: ast.AST) -> bool:
    """True if the module references ``contextvars.copy_context`` (the
    documented thread context-propagation escape hatch)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "copy_context":
            return True
        if isinstance(node, ast.Name) and node.id == "copy_context":
            return True
    return False


def _module_offends(source: str) -> bool:
    """A module offends when it spawns a raw thread AND starts a fresh
    event loop inside it, but never propagates context via copy_context."""
    tree = ast.parse(source)
    return (
        _spawns_raw_thread(tree) and _starts_fresh_event_loop(tree) and not _uses_copy_context(tree)
    )


@pytest.fixture(scope="module")
def offending_files() -> list[Path]:
    offenders: list[Path] = []
    for py_file in _iter_ingestion_files():
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            if _module_offends(source):
                offenders.append(py_file)
        except SyntaxError:
            continue
    return offenders


class TestNoUnguardedIngestionThreadHops:
    """Ingestion raw-thread hops that start a fresh event loop must
    propagate the active OTEL/Langfuse context via copy_context (#2251)."""

    def test_no_unguarded_ingestion_threadhop_files(self, offending_files: list[Path]) -> None:
        if not offending_files:
            return
        report = "\n".join(f"  - {p.relative_to(REPO_ROOT).as_posix()}" for p in offending_files)
        pytest.fail(
            "Found ingestion modules that spawn a raw thread + asyncio.run "
            "without contextvars.copy_context propagation. This orphans "
            "downstream @observe spans from the ingestion trace (see #2251). "
            "Capture contextvars.copy_context() on the parent and run the "
            "worker via ctx.run(...).\n\nOffending modules:\n" + report
        )


class TestScannerIsNotVacuous:
    """Guard the contract against silently going green if the scan path
    or the ingestion package layout changes."""

    def test_ingestion_dir_exists_and_scanned(self) -> None:
        assert INGESTION_DIR.exists(), f"ingestion dir not found: {INGESTION_DIR}"
        assert _iter_ingestion_files(), "scanner found 0 ingestion modules"

    def test_cocoindex_flow_is_scanned(self) -> None:
        scanned = {p.name for p in _iter_ingestion_files()}
        assert "cocoindex_flow.py" in scanned, (
            "cocoindex_flow.py is the canonical raw-thread-hop module; if it "
            "moved, update this contract."
        )


class TestContractCatchesRegressions:
    """Negative-path tests: feed the AST helpers synthetic snippets and
    verify unguarded hops are flagged and guarded hops are accepted."""

    _UNGUARDED_THREAD = (
        "import asyncio, threading\n"
        "def _runner():\n"
        "    asyncio.run(_update())\n"
        "threading.Thread(target=_runner).start()\n"
    )
    _UNGUARDED_SUBMIT = (
        "import asyncio, concurrent.futures\n"
        "with concurrent.futures.ThreadPoolExecutor() as pool:\n"
        "    pool.submit(asyncio.run, _embed())\n"
    )
    _GUARDED_THREAD = (
        "import asyncio, threading, contextvars\n"
        "ctx = contextvars.copy_context()\n"
        "def _runner():\n"
        "    asyncio.run(_update())\n"
        "threading.Thread(target=lambda: ctx.run(_runner)).start()\n"
    )
    _GUARDED_SUBMIT = (
        "import asyncio, concurrent.futures, contextvars\n"
        "with concurrent.futures.ThreadPoolExecutor() as pool:\n"
        "    ctx = contextvars.copy_context()\n"
        "    pool.submit(ctx.run, asyncio.run, _embed())\n"
    )
    _NO_THREADS = "import asyncio\nasync def f():\n    return await asyncio.to_thread(_embed)\n"

    def test_unguarded_thread_is_flagged(self) -> None:
        assert _module_offends(self._UNGUARDED_THREAD)

    def test_unguarded_submit_is_flagged(self) -> None:
        assert _module_offends(self._UNGUARDED_SUBMIT)

    def test_guarded_thread_is_accepted(self) -> None:
        assert not _module_offends(self._GUARDED_THREAD)

    def test_guarded_submit_is_accepted(self) -> None:
        assert not _module_offends(self._GUARDED_SUBMIT)

    def test_module_without_threads_is_accepted(self) -> None:
        assert not _module_offends(self._NO_THREADS)
