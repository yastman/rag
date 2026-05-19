"""Contract test: production code must not use deprecated `asyncio.get_event_loop()`.

`asyncio.get_event_loop()` is deprecated in Python 3.12+ and will raise
RuntimeError when no loop is running starting Python 3.14
(see Python whatsnew/3.14 / asyncio-eventloop docs).

Preferred replacements (verified via Context7 /python/cpython):
- Inside `async def`: use `asyncio.get_running_loop()`.
- Move blocking sync work off the loop: use `asyncio.to_thread(...)`.
- Sync-async bridge with multiple awaits: use `asyncio.Runner()` (3.11+).

This test scans production paths (src/, scripts/, telegram_bot/, mini_app/,
services/) for `asyncio.get_event_loop(` calls and reports every offender,
EXCEPT a small allowlist of legacy LangChain sync-bridge wrappers tracked
under #1639 follow-up. The allowlist must shrink, never grow.

Refs #1639.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS = [
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
]

# Frozen allowlist: legacy sync-bridge wrappers around long-lived
# httpx.AsyncClient. Removing or rewriting them requires deciding
# whether to drop sync support or build a tested sync-async boundary
# that does not break shared async resources. Tracked under #1639.
ALLOWLIST: dict[str, set[int]] = {
    "telegram_bot/integrations/embeddings.py": {59, 62, 179, 182},
}


def _iter_python_files(directories: list[Path]) -> list[Path]:
    files: list[Path] = []
    for d in directories:
        if not d.exists():
            continue
        files.extend(p for p in d.rglob("*.py") if "/.venv/" not in str(p))
    return files


def _find_get_event_loop_calls(
    source: str, file_path: Path
) -> list[tuple[Path, int]]:
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []
    offenders: list[tuple[Path, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get_event_loop":
            offenders.append((file_path, node.lineno))
    return offenders


def test_no_unallowlisted_get_event_loop_calls() -> None:
    """Production code may not introduce new `asyncio.get_event_loop()` callsites.

    Existing callsites listed in ALLOWLIST are tolerated until #1639
    follow-up resolves the LangChain sync-bridge question. Anything outside
    the allowlist must be migrated to get_running_loop / to_thread / Runner.
    """
    new_offenders: list[tuple[Path, int]] = []
    stale_allowlist: list[tuple[str, int]] = []

    for py_file in _iter_python_files(SCAN_DIRS):
        rel = str(py_file.relative_to(REPO_ROOT))
        offenders = _find_get_event_loop_calls(py_file.read_text(), py_file)
        allowed_lines = ALLOWLIST.get(rel, set())
        for path, lineno in offenders:
            if lineno not in allowed_lines:
                new_offenders.append((path, lineno))

    # Detect stale entries: allowlist points to a line that no longer
    # has a `get_event_loop` call. Forces the allowlist to shrink as
    # callsites are migrated.
    for rel, allowed_lines in ALLOWLIST.items():
        py_file = REPO_ROOT / rel
        if not py_file.exists():
            for lineno in allowed_lines:
                stale_allowlist.append((rel, lineno))
            continue
        actual = {ln for _, ln in _find_get_event_loop_calls(py_file.read_text(), py_file)}
        for lineno in allowed_lines:
            if lineno not in actual:
                stale_allowlist.append((rel, lineno))

    msgs: list[str] = []
    if new_offenders:
        msgs.append(
            "New asyncio.get_event_loop() calls outside the allowlist (#1639):\n"
            + "\n".join(
                f"  {p.relative_to(REPO_ROOT)}:{lineno}" for p, lineno in new_offenders
            )
            + "\nReplace with asyncio.get_running_loop() (in async),"
            " asyncio.to_thread(...) (blocking sync work),"
            " or asyncio.Runner() (sync-async bridge)."
        )
    if stale_allowlist:
        msgs.append(
            "Stale ALLOWLIST entries — remove from the dict in this test (#1639):\n"
            + "\n".join(f"  {rel}:{lineno}" for rel, lineno in stale_allowlist)
        )

    if msgs:
        raise AssertionError("\n\n".join(msgs))
