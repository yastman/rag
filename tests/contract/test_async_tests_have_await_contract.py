"""Contract: ``async def test_*`` functions must use at least one async feature (#1515 S2).

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
* New ``async def test_*`` functions that lack any async usage fail the
  contract immediately, prompting the author to either remove ``async``
  or add the missing async usage.

The detection accepts any of:

* ``await EXPR`` (``ast.Await``)
* ``async with CTX`` (``ast.AsyncWith``)
* ``async for X in IT`` (``ast.AsyncFor``)
* ``yield`` inside an async function (async generator)

If a test legitimately exercises an async context manager via ``async
with`` (e.g. FastAPI ``lifespan``), it is *not* an offender — keeping
``async def`` is the only way to consume it.

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
ALLOWLIST: frozenset[str] = frozenset()


def _collect_offenders() -> set[str]:
    """Return the set of ``relative_path::function_name`` for every async test
    under ``tests/unit/`` whose body does not use any async feature.

    "Async feature" means at least one of: ``await``, ``async with``,
    ``async for``, or ``yield`` (async generator).
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
            has_async_use = any(
                isinstance(
                    child,
                    (ast.Await, ast.AsyncWith, ast.AsyncFor, ast.Yield, ast.YieldFrom),
                )
                for child in ast.walk(node)
            )
            if not has_async_use:
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.add(f"{rel}::{node.name}")
    return offenders


def test_no_new_async_tests_without_await() -> None:
    """New ``async def test_*`` functions must use at least one async feature.

    Either drop ``async`` (the test is sync) or add the missing async
    usage (``await``, ``async with``, ``async for``, or ``yield``).
    """
    offenders = _collect_offenders()
    new_offenders = sorted(offenders - ALLOWLIST)
    assert not new_offenders, (
        "#1515 S2: new async test(s) without any async usage detected. "
        "Convert to a plain `def test_*` if the body is sync, or add the "
        "missing `await` / `async with` / `async for` if it should "
        "genuinely exercise async code.\n"
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
