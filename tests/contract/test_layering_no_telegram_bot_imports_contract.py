"""Contract: ratchet allowlist for ``src/`` and ``mini_app/`` imports of ``telegram_bot`` (#1948).

Project layout intent (`README`, `pyproject.toml`):

* ``src/*`` — reusable RAG library, **must not import** ``telegram_bot``.
* ``mini_app/*`` — Telegram Mini App backend (separate Docker image), **must
  not import** ``telegram_bot``.
* ``telegram_bot/*`` — the bot application, **may** import from ``src/*``.

Reality (issue #1948): ``src/api/main.py`` and ``mini_app/{api,phone}.py``
import from ``telegram_bot.*`` and the Dockerfiles for both services copy
``telegram_bot/`` into the image to make the imports resolve.

The full migration is multi-PR (each shared module has to be relocated and
re-exported with care). This contract is the **ratchet** that lets the
migration land incrementally:

* ``tests/data/known_layering_violations.json`` lists every file with its
  current set of ``telegram_bot.*`` imports.
* This test fails when **a new file** introduces a forbidden import or
  **an existing file gains** a new import path that is not already in the
  allowlist.
* The allowlist must shrink over time; never regenerate it to silence a
  failure (mirror of the duplicate-test-name guard in #1539).

When you fix a violation, remove the corresponding entry from the JSON
file. The test enforces the smaller surface immediately.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO_ROOT / "tests" / "data" / "known_layering_violations.json"

# Subtrees that must not depend on telegram_bot.
GUARDED_ROOTS = ("src", "mini_app")


def _collect_violations() -> dict[str, list[str]]:
    """Return ``{relative_file_path: sorted([forbidden_module, ...])}``."""
    out: dict[str, list[str]] = {}
    for root_name in GUARDED_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            forbidden: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod == "telegram_bot" or mod.startswith("telegram_bot."):
                        forbidden.add(mod)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name
                        if name == "telegram_bot" or name.startswith("telegram_bot."):
                            forbidden.add(name)
            if forbidden:
                out[path.relative_to(REPO_ROOT).as_posix()] = sorted(forbidden)
    return out


def _load_allowlist() -> dict[str, list[str]]:
    if not ALLOWLIST_PATH.exists():
        return {}
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {k: sorted(v) for k, v in payload.items()}


def test_no_new_files_import_telegram_bot_under_src_or_mini_app() -> None:
    current = _collect_violations()
    allowlist = _load_allowlist()
    new_files = sorted(set(current) - set(allowlist))
    assert not new_files, (
        "#1948: new file(s) under src/ or mini_app/ import from telegram_bot. The "
        "package boundary forbids reverse layering. Fix the import (move the shared "
        "module under src/ or factor the surface) before merging. New files: "
        f"{new_files}"
    )


def test_existing_violation_files_do_not_grow() -> None:
    current = _collect_violations()
    allowlist = _load_allowlist()
    grown: dict[str, list[str]] = {}
    for path, allowed in allowlist.items():
        if path not in current:
            # File became compliant; the dedicated test below catches stale
            # allowlist entries.
            continue
        added = sorted(set(current[path]) - set(allowed))
        if added:
            grown[path] = added
    assert not grown, (
        "#1948: existing file(s) under src/ or mini_app/ added a NEW telegram_bot "
        "import that is not in the allowlist. Either remove the new import or, if "
        "the migration legitimately requires it, document why and update the JSON "
        f"explicitly. Grown: {grown}"
    )


def test_allowlist_does_not_list_already_compliant_files() -> None:
    current = _collect_violations()
    allowlist = _load_allowlist()
    stale = sorted(set(allowlist) - set(current))
    assert not stale, (
        "#1948: known_layering_violations.json lists files that no longer import "
        "telegram_bot. Remove these stale entries to keep the ratchet honest: "
        f"{stale}"
    )


def test_allowlist_modules_match_current_for_unchanged_files() -> None:
    """For files in the allowlist that still violate, the listed modules must match
    exactly. This catches accidental allowlist drift where a module was renamed in
    the allowlist but not removed from the actual import."""
    current = _collect_violations()
    allowlist = _load_allowlist()
    drift: dict[str, dict[str, list[str]]] = {}
    for path, allowed in allowlist.items():
        if path not in current:
            continue
        current_set = set(current[path])
        allowed_set = set(allowed)
        if current_set != allowed_set:
            drift[path] = {
                "extra_in_allowlist": sorted(allowed_set - current_set),
                "missing_from_allowlist": sorted(current_set - allowed_set),
            }
    assert not drift, (
        "#1948: known_layering_violations.json drift detected. Update the entry to "
        f"match the current import set exactly: {drift}"
    )
