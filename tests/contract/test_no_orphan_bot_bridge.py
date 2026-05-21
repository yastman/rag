"""Contract: ``mini_app.bot_bridge`` is removed and not reintroduced (#1615).

The Mini App runtime start flow uses a Redis pub/sub bridge between
``mini_app/api.py`` and ``telegram_bot/bot.py``. ``mini_app/bot_bridge.py``
defined a parallel direct-bot bridge (``BotBridge`` + ``set_bot_bridge`` +
``get_bot_bridge``) that never had a runtime caller — only the unit test
``tests/unit/mini_app/test_bot_bridge.py``. Two apparent integration
surfaces with one wired to runtime is the maintenance hazard #1615
called out.

This contract pins the cleanup:

1. ``mini_app/bot_bridge.py`` does not exist.
2. ``tests/unit/mini_app/test_bot_bridge.py`` does not exist.
3. No runtime Python under ``mini_app/`` or ``telegram_bot/`` imports
   from a ``bot_bridge`` module.

If a Mini App ↔ bot bridge is ever needed again, this contract requires
the new approach to be wired into runtime startup with a real test, not
sit alongside the active Redis path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "mini_app" / "bot_bridge.py",
    REPO_ROOT / "tests" / "unit" / "mini_app" / "test_bot_bridge.py",
)

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+\S*bot_bridge\s+import|import\s+\S*bot_bridge)\b",
    re.MULTILINE,
)


@pytest.mark.parametrize(
    "path", FORBIDDEN_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_orphan_bot_bridge_files_are_absent(path: Path) -> None:
    if path.exists():
        raise AssertionError(
            f"'{path.relative_to(REPO_ROOT)}' has reappeared. The Mini App "
            "↔ bot integration is owned by the Redis pub/sub path "
            "(mini_app/api.py + telegram_bot/bot.py); a parallel BotBridge "
            "module created the maintenance hazard #1615 called out."
        )


def test_no_runtime_import_of_bot_bridge() -> None:
    """No runtime module under mini_app/ or telegram_bot/ may import bot_bridge (#1615)."""
    runtime_roots = (REPO_ROOT / "mini_app", REPO_ROOT / "telegram_bot")
    offenders: list[str] = []
    for root in runtime_roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            try:
                text = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in _IMPORT_RE.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(
                    f"{py_file.relative_to(REPO_ROOT)}:{line_no}: "
                    f"{match.group(0).strip()}"
                )
    assert not offenders, (
        "Runtime code imports a bot_bridge module. The Mini App ↔ bot "
        "integration must stay on the Redis pub/sub path or come back as "
        "a single, wired-in module with explicit runtime ownership.\n"
        "Imports found:\n  - " + "\n  - ".join(offenders)
    )
