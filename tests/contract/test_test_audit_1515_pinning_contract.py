"""Test infrastructure audit pinning contract (#1515).

Issue #1515 audited the test suite and called out six concrete bugs
(B1..B6) plus a series of duplicate / smell observations. By the time
this contract is added to ``dev`` the audit's B1, B3, B4, B5, B6 are
already resolved on disk. This contract pins those resolutions so a
future change cannot silently regress them.

Pinned invariants:

- **B1**: ``tests/conftest.py`` and ``tests/smoke/conftest.py`` must not
  introduce new ``asyncio.get_event_loop()`` calls in non-mock contexts.
- **B5**: ``tests/conftest.py::pytest_collection_modifyitems`` must apply
  directory markers to every advertised test tier (``unit``,
  ``integration``, ``smoke``, ``e2e``, ``chaos``, ``load``,
  ``benchmark``, ``contract``, ``baseline``) so ``-m <tier>`` filtering
  works end-to-end.
- **B6**: ``pyproject.toml`` coverage omit must exclude
  ``telegram_bot/.venv/*`` so a stray local venv does not pollute the
  coverage source set.

Companion contract ``tests/contract/test_no_get_event_loop.py`` already
covers production code (src/, scripts/, telegram_bot/, mini_app/,
services/). This contract complements it by covering the *test suite
infrastructure* surface that #1515 specifically named.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# B1 pin: no raw asyncio.get_event_loop() in conftest sync paths
# ---------------------------------------------------------------------------


def _find_unmocked_get_event_loop(source: str, path: Path) -> list[int]:
    """Return line numbers of `asyncio.get_event_loop(...)` *call expressions*
    in the given source, excluding `patch("asyncio.get_event_loop")` mock
    targets and string occurrences inside other call args.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match: asyncio.get_event_loop()  / loop.get_event_loop()
        if isinstance(func, ast.Attribute) and func.attr == "get_event_loop":
            offenders.append(node.lineno)
    return offenders


@pytest.mark.parametrize(
    "rel_path",
    [
        "tests/conftest.py",
        "tests/smoke/conftest.py",
    ],
)
def test_no_get_event_loop_in_test_conftests(rel_path: str) -> None:
    """B1 pin: no `asyncio.get_event_loop()` call expressions in conftests."""
    path = REPO_ROOT / rel_path
    if not path.exists():
        pytest.skip(f"{rel_path} not present in this checkout")
    offenders = _find_unmocked_get_event_loop(path.read_text(), path)
    assert offenders == [], (
        f"B1 regression (#1515): {rel_path} reintroduced "
        f"asyncio.get_event_loop() at line(s) {offenders}. Use "
        f"asyncio.run(...) or asyncio.get_running_loop() instead."
    )


# ---------------------------------------------------------------------------
# B5 pin: path_to_marker covers every advertised test tier
# ---------------------------------------------------------------------------


REQUIRED_TIER_MARKERS = frozenset(
    {
        "unit",
        "integration",
        "smoke",
        "e2e",
        "chaos",
        "load",
        "benchmark",
        "contract",
        "baseline",
    }
)


def test_root_conftest_path_to_marker_covers_all_tiers() -> None:
    """B5 pin: `pytest_collection_modifyitems` maps every tier directory."""
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text()
    # Match `root / "<dir>": "<marker>",` style entries.
    entries = set(re.findall(r'root\s*/\s*"([^"]+)"\s*:\s*"([^"]+)"', conftest))
    if not entries:
        pytest.skip("path_to_marker dict shape changed; update this contract")
    mapped_dirs = {dir_name for dir_name, _ in entries}
    missing = REQUIRED_TIER_MARKERS - mapped_dirs
    assert not missing, (
        f"B5 regression (#1515): tests/conftest.py::pytest_collection_modify"
        f"items is missing directory entries for {sorted(missing)}. Tests in "
        f"these directories cannot be filtered with `-m <tier>`."
    )


# ---------------------------------------------------------------------------
# B6 pin: coverage omit excludes the bot-local .venv
# ---------------------------------------------------------------------------


def test_coverage_omit_excludes_bot_local_venv() -> None:
    """B6 pin: `[tool.coverage.run].omit` excludes telegram_bot/.venv paths.

    The bot package historically had a co-located venv. If a developer
    creates one again, coverage must not scan it as production source.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_bytes()
    data = tomllib.loads(pyproject.decode())
    omit = data.get("tool", {}).get("coverage", {}).get("run", {}).get("omit", [])
    omit_set = set(omit)
    required = {"telegram_bot/.venv/*", "telegram_bot/.venv/**/*"}
    missing = required - omit_set
    # Tolerate equivalent broader patterns.
    if missing and any(p in omit_set for p in ("*/.venv/*", "**/.venv/**", "*.venv/*")):
        return
    assert not missing, (
        f"B6 regression (#1515): pyproject.toml [tool.coverage.run].omit "
        f"missing {sorted(missing)}. Without this, a stray "
        f"telegram_bot/.venv/ pollutes coverage with site-packages."
    )
