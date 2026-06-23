"""Contract test for #1515 D6 — BotConfig duplicate tests.

The May 13 test audit (#1515 — D6) flagged two byte-identical duplicates that
existed in both ``tests/unit/test_settings.py`` (under
``TestBotConfigBoolFields``) and the canonical home
``tests/unit/config/test_bot_config_settings.py``:

    - test_config_bool_fields_parse_env_strings
    - test_config_get_collection_name

Both are pytest-collected. Under ``pytest-xdist`` they would silently merge or
skip via ``known_duplicate_test_names.json``. The fix removes them from
``tests/unit/test_settings.py`` and tightens the duplicate-name ratchet.

This contract pins the deletion: it walks the test tree with AST and asserts
that each name lives in exactly one canonical file. Future drift (someone
recreating the duplicate or moving the canonical implementation) breaks the
test.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = REPO_ROOT / "tests"
ALLOWLIST_PATH = TESTS_DIR / "data" / "known_duplicate_test_names.json"

# Names that #1515 D6 deletes from tests/unit/test_settings.py.
# Each maps to its **single** canonical home after the fix.
DEDUPED_TESTS: dict[str, str] = {
    "test_config_bool_fields_parse_env_strings": ("tests/unit/config/test_bot_config_settings.py"),
    "test_config_get_collection_name": ("tests/unit/config/test_bot_config_settings.py"),
}


def _collect_files_defining(name: str) -> list[str]:
    """Return repo-relative paths of every test file that defines ``name``.

    Walks every ``test_*.py`` under ``tests/`` and matches both
    ``def`` and ``async def`` at module or class scope.
    """
    matches: list[str] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                matches.append(path.relative_to(REPO_ROOT).as_posix())
                break
    return matches


@pytest.mark.parametrize(("name", "canonical"), sorted(DEDUPED_TESTS.items()))
def test_deduped_test_lives_only_in_canonical_home(name: str, canonical: str) -> None:
    """Each #1515 D6 test must live in exactly one file."""
    files = _collect_files_defining(name)
    assert files == [canonical], (
        f"#1515 D6 regression: {name} must live only in {canonical}, found in {files}"
    )


@pytest.mark.parametrize("name", sorted(DEDUPED_TESTS))
def test_deduped_name_not_in_known_duplicate_allowlist(name: str) -> None:
    """After the fix, the ratchet allowlist must not list the name anymore."""
    allowlist = json.loads(ALLOWLIST_PATH.read_text())
    assert name not in allowlist, (
        f"#1515 D6 regression: {name} should be removed from "
        f"{ALLOWLIST_PATH.relative_to(REPO_ROOT)} after dedup; still present."
    )


def test_canonical_file_still_exists() -> None:
    """Sanity guard: the canonical home file must still be present."""
    canonical = REPO_ROOT / "tests/unit/config/test_bot_config_settings.py"
    assert canonical.exists(), (
        "tests/unit/config/test_bot_config_settings.py must remain — it is "
        "the canonical home for BotConfig settings tests after #1515 D6."
    )
