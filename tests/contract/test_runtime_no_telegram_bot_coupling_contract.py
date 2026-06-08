"""Contract: ratchet dynamic ``telegram_bot`` coupling under ``src.core``/``src.runtime``.

The static layering contract already blocks ``import telegram_bot`` statements
under ``src``. This contract covers the remaining runtime-coupling seam: string
literals such as ``importlib.import_module("telegram_bot...")`` and default
factory specs that still point back to the Telegram adapter package during the
monolith-core migration.

The allowlist is intentionally small and must shrink as CORE-004/CORE-005 move
generation/RAG ownership into ``src.runtime`` and CORE-010 removes transitional
shims/defaults.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO_ROOT / "tests" / "data" / "known_runtime_telegram_bot_couplings.json"
GUARDED_ROOTS = (REPO_ROOT / "src" / "core", REPO_ROOT / "src" / "runtime")


def _load_allowlist() -> dict[str, list[str]]:
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {path: sorted(values) for path, values in payload.items()}


def _docstring_nodes(tree: ast.AST) -> set[ast.Constant]:
    out: set[ast.Constant] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                out.add(first.value)
    return out


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str) and "telegram_bot." in value:
        return [value]
    return []


def _collect_runtime_couplings() -> dict[str, list[str]]:
    out: dict[str, set[str]] = {}
    for root in GUARDED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = _docstring_nodes(tree)
            values: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node not in docstrings:
                    values.update(_string_values(node.value))
                elif isinstance(node, ast.JoinedStr):
                    # Dynamic f-strings containing telegram_bot are forbidden even
                    # if the exact final module path is not statically knowable.
                    literal_parts = [
                        part.value
                        for part in node.values
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    ]
                    joined = "".join(literal_parts)
                    values.update(_string_values(joined))
            if values:
                out[path.relative_to(REPO_ROOT).as_posix()] = values
    return {path: sorted(values) for path, values in out.items()}


def test_no_new_files_add_runtime_telegram_bot_coupling() -> None:
    current = _collect_runtime_couplings()
    allowlist = _load_allowlist()
    new_files = sorted(set(current) - set(allowlist))
    assert not new_files, (
        "CORE-003: new file(s) under src/core or src/runtime contain executable "
        "telegram_bot.* string coupling. Move the shared code under src.runtime or "
        f"explicitly justify a temporary allowlist entry. New files: {new_files}"
    )


def test_existing_runtime_telegram_bot_coupling_does_not_grow() -> None:
    current = _collect_runtime_couplings()
    allowlist = _load_allowlist()
    grown: dict[str, list[str]] = {}
    for path, allowed_values in allowlist.items():
        added = sorted(set(current.get(path, [])) - set(allowed_values))
        if added:
            grown[path] = added
    assert not grown, (
        "CORE-003: existing runtime coupling file(s) added new telegram_bot.* "
        f"strings. Added values: {grown}"
    )


def test_runtime_telegram_bot_coupling_allowlist_has_no_stale_files() -> None:
    current = _collect_runtime_couplings()
    allowlist = _load_allowlist()
    stale = sorted(set(allowlist) - set(current))
    assert not stale, (
        "CORE-003: allowlist contains file(s) that no longer have executable "
        f"telegram_bot.* string coupling. Remove stale entries: {stale}"
    )


def test_runtime_telegram_bot_coupling_allowlist_matches_current_values() -> None:
    current = _collect_runtime_couplings()
    allowlist = _load_allowlist()
    drift: dict[str, dict[str, list[str]]] = {}
    for path, allowed_values in allowlist.items():
        if path not in current:
            continue
        current_set = set(current[path])
        allowed_set = set(allowed_values)
        if current_set != allowed_set:
            drift[path] = {
                "extra_in_allowlist": sorted(allowed_set - current_set),
                "missing_from_allowlist": sorted(current_set - allowed_set),
            }
    assert not drift, (
        "CORE-003: runtime coupling allowlist drift detected. Update the JSON "
        f"to match current executable telegram_bot.* strings exactly: {drift}"
    )


if __name__ == "__main__":
    test_no_new_files_add_runtime_telegram_bot_coupling()
    test_existing_runtime_telegram_bot_coupling_does_not_grow()
    test_runtime_telegram_bot_coupling_allowlist_has_no_stale_files()
    test_runtime_telegram_bot_coupling_allowlist_matches_current_values()
