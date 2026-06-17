"""Contract: archive/voice must not import live telegram_bot code or deleted src.voice namespace.

Audit finding from #2712. Two classes of stale imports exist in archive/voice/:

1. archive/voice/voice_agent.py imports telegram_bot.agents.* (live code).
2. archive/voice/agent.py and archive/voice/transcript_store.py import src.voice.* (deleted namespace).

Closes #2748.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_VOICE_ROOT = REPO_ROOT / "archive" / "voice"

FORBIDDEN_PREFIXES = ("telegram_bot", "src.voice")


def _collect_forbidden_imports(path: Path) -> list[str]:
    """Return list of forbidden import module strings found in file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for prefix in FORBIDDEN_PREFIXES:
                if mod == prefix or mod.startswith(prefix + "."):
                    found.append(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_PREFIXES:
                    if alias.name == prefix or alias.name.startswith(prefix + "."):
                        found.append(alias.name)
    return found


def test_archive_voice_does_not_import_telegram_bot_or_deleted_src_voice() -> None:
    """archive/voice/ must not import live telegram_bot code or deleted src.voice namespace."""
    violations: dict[str, list[str]] = {}
    if not ARCHIVE_VOICE_ROOT.exists():
        return
    for path in sorted(ARCHIVE_VOICE_ROOT.rglob("*.py")):
        forbidden = _collect_forbidden_imports(path)
        if forbidden:
            violations[path.relative_to(REPO_ROOT).as_posix()] = sorted(set(forbidden))

    assert not violations, (
        "#2748: archive/voice/ files import from live telegram_bot code or deleted "
        "src.voice namespace. Fix by using local archive/voice/ modules or self-contained "
        f"stubs. Violations: {violations}"
    )
