"""Bound check for the draft_streamer regression scanner (#2198).

The scanner in ``test_no_production_references_to_draft_streamer_module``
used ``REPO_ROOT.rglob('*.py')`` which traversed ``.venv``, worktrees,
caches, and ``node_modules`` before filtering. On a local checkout this
exceeded the 30s pytest-timeout. The scanner must be bound to known
production source roots and complete well under the timeout.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.unit.services.test_draft_streamer_removed import (
    _scan_production_for_draft_streamer_references,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_scanner_completes_well_under_30s_timeout() -> None:
    """The scanner must finish in a small fraction of the 30s timeout
    even on a local checkout with .venv, .worktrees, and caches present.
    """
    start = time.perf_counter()
    refs = _scan_production_for_draft_streamer_references(REPO_ROOT)
    elapsed = time.perf_counter() - start

    # The pytest-timeout is 30s; we want a comfortable margin for slow CI.
    assert elapsed < 10.0, (
        f"draft_streamer scanner took {elapsed:.2f}s; must complete under 10s "
        f"(pytest-timeout is 30s and the fast gate runs >7000 tests)"
    )
    # No production refs expected on a clean tree.
    assert refs == [], f"unexpected production references: {refs}"


def test_scanner_skips_dot_venv_even_when_inside_repo_root(tmp_path: Path) -> None:
    """`.venv/` (or any noise dir) under REPO_ROOT must not be traversed,
    even when it contains files matching the search string.
    """
    # Synthesise a minimal repo-shaped layout.
    (tmp_path / "telegram_bot").mkdir()
    (tmp_path / "telegram_bot" / "bot.py").write_text("# clean production code\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "stub.py").write_text("# clean\n", encoding="utf-8")

    # Stage many files under .venv that would slow rglob and contain the
    # banned token. The scanner must NOT see them.
    venv = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    venv.mkdir(parents=True)
    for i in range(100):
        (venv / f"poison_{i}.py").write_text(
            "import telegram_bot.services.draft_streamer\n", encoding="utf-8"
        )

    refs = _scan_production_for_draft_streamer_references(tmp_path)
    assert refs == [], f"scanner descended into .venv and reported {len(refs)} false positives"


def test_scanner_still_catches_real_production_reference(tmp_path: Path) -> None:
    """Real production references in telegram_bot/ or src/ are still flagged."""
    (tmp_path / "telegram_bot").mkdir()
    (tmp_path / "telegram_bot" / "bot.py").write_text(
        "import telegram_bot.services.draft_streamer\n", encoding="utf-8"
    )

    refs = _scan_production_for_draft_streamer_references(tmp_path)
    assert refs and any("bot.py" in r for r in refs), (
        f"scanner missed a real production reference; refs={refs}"
    )


def test_scanner_ignores_test_and_script_paths(tmp_path: Path) -> None:
    """tests/ and scripts/ paths legitimately mention the symbol name."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "from telegram_bot.services.draft_streamer import X\n", encoding="utf-8"
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "foo.py").write_text(
        "# notes about telegram_bot.services.draft_streamer\n", encoding="utf-8"
    )

    refs = _scan_production_for_draft_streamer_references(tmp_path)
    assert refs == [], f"scanner falsely flagged tests/scripts paths: {refs}"


@pytest.mark.parametrize("source_root", ["telegram_bot", "src"])
def test_scanner_scopes_to_known_production_roots(source_root: str, tmp_path: Path) -> None:
    """Each declared production root must be scanned."""
    (tmp_path / source_root).mkdir()
    (tmp_path / source_root / "leak.py").write_text(
        "from telegram_bot.services.draft_streamer import Streamer\n",
        encoding="utf-8",
    )

    refs = _scan_production_for_draft_streamer_references(tmp_path)
    assert any(source_root in r for r in refs), (
        f"production root {source_root} not scanned; refs={refs}"
    )
