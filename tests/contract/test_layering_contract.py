"""Contract: src/core/ and src/runtime/ must not import from telegram_bot (#2846).

Layering rule (ADR #2846, docs/designs/adr-2846-layering.md):

    src/core/     — reusable RAG core; allowed: python stdlib + third-party only
    src/runtime/  — reusable runtime pipeline; allowed: src/core, third-party
    telegram_bot/ — bot application adapter; allowed: src/*, third-party

Reverse imports (telegram_bot → src direction inverted) break SDK reusability,
deployment isolation, and test isolation.  This test enforces a hard zero-
tolerance boundary: no file under src/core/ or src/runtime/ may contain a
static ``import telegram_bot`` or ``from telegram_bot`` statement.

Unlike the ratchet allowlist in test_layering_no_telegram_bot_imports_contract.py
(which covers all of src/ with legacy exceptions), this test enforces the strict
rule for the two innermost layers that must always remain clean.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STRICT_ROOTS = (
    REPO_ROOT / "src" / "core",
    REPO_ROOT / "src" / "runtime",
)


def _find_telegram_bot_imports(path: Path) -> list[str]:
    """Return sorted list of forbidden telegram_bot import strings found in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "telegram_bot" or mod.startswith("telegram_bot."):
                found.add(f"from {mod} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "telegram_bot" or alias.name.startswith("telegram_bot."):
                    found.add(f"import {alias.name}")
    return sorted(found)


def test_core_does_not_import_telegram_bot() -> None:
    """src/core/ must have zero static telegram_bot imports."""
    violations: dict[str, list[str]] = {}
    root = REPO_ROOT / "src" / "core"
    if root.exists():
        for path in sorted(root.rglob("*.py")):
            imports = _find_telegram_bot_imports(path)
            if imports:
                violations[path.relative_to(REPO_ROOT).as_posix()] = imports
    assert not violations, (
        "#2846: src/core/ must not import from telegram_bot. "
        "The core layer is a reusable SDK; reverse-layer coupling breaks "
        "deployment isolation and test isolation. Fix by moving shared code "
        f"under src/ or inverting the dependency. Violations: {violations}"
    )


def test_runtime_does_not_import_telegram_bot() -> None:
    """src/runtime/ must have zero static telegram_bot imports."""
    violations: dict[str, list[str]] = {}
    root = REPO_ROOT / "src" / "runtime"
    if root.exists():
        for path in sorted(root.rglob("*.py")):
            imports = _find_telegram_bot_imports(path)
            if imports:
                violations[path.relative_to(REPO_ROOT).as_posix()] = imports
    assert not violations, (
        "#2846: src/runtime/ must not import from telegram_bot. "
        "The runtime pipeline layer must stay decoupled from bot adapter code. "
        "Fix by moving shared code under src/ or inverting the dependency. "
        f"Violations: {violations}"
    )
