"""Contract test for issue #2066 — smoke fixtures must use shared config.

Issue #1515 audit D3+D4 flagged that ``tests/smoke/conftest.py`` had its
own ``redis_url`` and Qdrant URL/collection fixtures that duplicated the
shared definitions in ``tests/fixtures/config.py`` (with subtly different
default values — the smoke copy used the production collection
``gdrive_documents_bge`` while the shared copy used ``test_documents``).

This contract locks in three invariants after the dedup:

1. ``tests/fixtures/config.py`` is registered as a pytest plugin from
   ``tests/conftest.py`` so its fixtures are visible repo-wide.
2. ``tests/fixtures/config.py::qdrant_collection`` defaults to the
   production contract value ``gdrive_documents_bge``, matching
   ``telegram_bot/config.py`` and ``compose.yml``.
3. ``tests/smoke/conftest.py`` does not redefine ``redis_url`` /
   ``qdrant_url`` / ``qdrant_api_key`` / ``qdrant_collection``. It may
   *consume* them from the shared plugin, but it must not redeclare them.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SHARED_FIXTURES = REPO / "tests" / "fixtures" / "config.py"
ROOT_CONFTEST = REPO / "tests" / "conftest.py"
SMOKE_CONFTEST = REPO / "tests" / "smoke" / "conftest.py"

SHARED_FIXTURE_NAMES = (
    "redis_url",
    "qdrant_url",
    "qdrant_api_key",
    "qdrant_collection",
)


def test_shared_config_fixtures_registered_in_root_conftest() -> None:
    text = ROOT_CONFTEST.read_text(encoding="utf-8")
    assert "tests.fixtures.config" in text, (
        "tests/conftest.py must register `tests.fixtures.config` as a "
        "pytest plugin so its session-scoped URL/collection fixtures are "
        "available to every test tier (issue #2066)."
    )


def test_qdrant_collection_default_matches_production_contract() -> None:
    text = SHARED_FIXTURES.read_text(encoding="utf-8")
    match = re.search(
        r"def qdrant_collection\([^)]*\):.*?return os\.getenv\(\s*\"QDRANT_COLLECTION\"\s*,\s*\"([^\"]+)\"\s*\)",
        text,
        re.DOTALL,
    )
    assert match, "qdrant_collection fixture not found in tests/fixtures/config.py"
    assert match.group(1) == "gdrive_documents_bge", (
        f"qdrant_collection default is {match.group(1)!r}; must be "
        "'gdrive_documents_bge' to match telegram_bot/config.py and "
        "compose.yml (issue #2066)."
    )


def test_smoke_conftest_does_not_redefine_shared_fixtures() -> None:
    text = SMOKE_CONFTEST.read_text(encoding="utf-8")
    # Strip docstrings and comments so we don't false-match prose.
    code_only_lines: list[str] = []
    in_string = False
    string_delim = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not in_string:
            if stripped.startswith(("#",)):
                continue
            triple = '"""' if '"""' in stripped else ("'''" if "'''" in stripped else "")
            if triple and stripped.count(triple) % 2 == 1:
                in_string = True
                string_delim = triple
                continue
        else:
            if string_delim in line:
                in_string = False
            continue
        code_only_lines.append(line)
    code = "\n".join(code_only_lines)

    redefined: list[str] = []
    for name in SHARED_FIXTURE_NAMES:
        # Match `def <name>(` only when preceded by a fixture decorator marker
        # (look back ~80 chars for `@pytest.fixture`).
        for m in re.finditer(rf"\bdef\s+{re.escape(name)}\s*\(", code):
            window = code[max(0, m.start() - 100) : m.start()]
            if "pytest.fixture" in window or "@fixture" in window:
                redefined.append(name)
                break

    assert redefined == [], (
        "tests/smoke/conftest.py redefines fixture(s) that are owned by "
        "tests/fixtures/config.py: "
        f"{redefined}. Drop the local copies and consume the shared "
        "session-scoped fixtures (issue #2066)."
    )
