"""Contract test for Mini App frontend cleanup (#1597).

Asserts three structural invariants on the React/Vite Mini App frontend:

1. ``src/guards/TelegramGate.tsx`` no longer hardcodes the Telegram bot
   handle ``FortnoksBot``. It MUST read the bot username from the
   Vite-exposed env var ``VITE_BOT_USERNAME`` and compose the link via a
   template literal (``https://t.me/${...}``).

2. ``package.json`` does not declare ``zustand`` in either ``dependencies``
   or ``devDependencies`` — the package is unused by ``src/``.

3. The dead ``submitPhone`` helper has been removed from ``src/api.ts``
   and is not declared, exported, or imported anywhere under
   ``mini_app/frontend/src/``.

Refs #1597.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "mini_app" / "frontend"
SRC_DIR = FRONTEND_DIR / "src"
TELEGRAM_GATE = SRC_DIR / "guards" / "TelegramGate.tsx"
PACKAGE_JSON = FRONTEND_DIR / "package.json"


def _iter_ts_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx"}]


def test_telegram_gate_uses_vite_bot_username_env_var() -> None:
    """TelegramGate must read VITE_BOT_USERNAME, not hardcode FortnoksBot."""
    if not TELEGRAM_GATE.exists():
        pytest.skip(f"{TELEGRAM_GATE} not present")

    text = TELEGRAM_GATE.read_text()

    assert "FortnoksBot" not in text, (
        "TelegramGate.tsx still hardcodes the bot handle 'FortnoksBot'. "
        "Replace with a config-driven link using import.meta.env.VITE_BOT_USERNAME."
    )
    assert "VITE_BOT_USERNAME" in text, (
        "TelegramGate.tsx must reference the Vite env var VITE_BOT_USERNAME to compose the bot URL."
    )
    assert "t.me/" in text, "TelegramGate.tsx should still link to the Telegram bot."
    # Template-literal interpolation: `${...}` somewhere in the file.
    assert "${" in text, (
        "TelegramGate.tsx must compose the bot URL via a template literal, "
        "e.g. `https://t.me/${import.meta.env.VITE_BOT_USERNAME ?? 'your_bot'}`."
    )


def test_package_json_does_not_depend_on_zustand() -> None:
    """zustand is unused under src/ and must not appear in package.json."""
    if not PACKAGE_JSON.exists():
        pytest.skip(f"{PACKAGE_JSON} not present")

    pkg = json.loads(PACKAGE_JSON.read_text())
    deps = pkg.get("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})

    assert "zustand" not in deps, (
        "zustand is declared in dependencies but is not imported anywhere "
        "under mini_app/frontend/src/. Remove it (#1597)."
    )
    assert "zustand" not in dev_deps, (
        "zustand is declared in devDependencies but is not imported "
        "anywhere under mini_app/frontend/src/. Remove it (#1597)."
    )


def test_submit_phone_helper_is_removed() -> None:
    """The dead submitPhone helper must not be defined or imported in src/."""
    if not SRC_DIR.exists():
        pytest.skip(f"{SRC_DIR} not present")

    # Match a definition or assignment: `submitPhone(`, `submitPhone =`,
    # or `function submitPhone`.
    def_pattern = re.compile(r"\bsubmitPhone\s*[(=]|function\s+submitPhone\b")
    # Match imports referencing the symbol.
    import_pattern = re.compile(r"import\s*\{[^}]*\bsubmitPhone\b[^}]*\}")

    def_offenders: list[str] = []
    import_offenders: list[str] = []

    for ts_file in _iter_ts_files(SRC_DIR):
        text = ts_file.read_text()
        rel = ts_file.relative_to(REPO_ROOT)
        if def_pattern.search(text):
            def_offenders.append(str(rel))
        if import_pattern.search(text):
            import_offenders.append(str(rel))

    assert not def_offenders, (
        "submitPhone is still defined/exported but has no callers. "
        "Remove it from: " + ", ".join(def_offenders)
    )
    assert not import_offenders, (
        "submitPhone is still imported but should be removed. "
        "Imports remain in: " + ", ".join(import_offenders)
    )
