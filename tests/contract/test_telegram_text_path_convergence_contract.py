"""Contract: Telegram text path is converged on the assistant core (#2630).

ARCH-16 removed the ASSISTANT_CORE_ENTRYPOINT_ENABLED env-flag fallback.
The assistant core is now the only text path; the old sdk-agent branch is gone.

Pins:
- The env-flag constant no longer exists in assistant_core_adapter.
- The guard predicate no longer exists in assistant_core_adapter.
- bot.py does not import either symbol.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "telegram_bot" / "assistant_core_adapter.py"
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"

REMOVED_SYMBOLS = {"CORE_ENTRYPOINT_ENV", "core_entrypoint_enabled"}


def _top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def test_adapter_no_longer_exports_entrypoint_flag() -> None:
    """CORE_ENTRYPOINT_ENV and core_entrypoint_enabled must not exist in adapter."""
    defined = _top_level_names(ADAPTER_PATH)
    present = sorted(REMOVED_SYMBOLS & defined)
    assert not present, (
        f"ARCH-16 (#2630): assistant_core_adapter still defines legacy symbols: {present}. "
        "The env-flag routing was removed; the core is always active."
    )


def test_bot_does_not_import_entrypoint_flag() -> None:
    """bot.py must not import the legacy flag symbols."""
    imported = _imported_names(BOT_PATH)
    present = sorted(REMOVED_SYMBOLS & imported)
    assert not present, (
        f"ARCH-16 (#2630): bot.py still imports legacy entrypoint flag symbols: {present}. "
        "The env-flag routing was removed; remove the import."
    )
