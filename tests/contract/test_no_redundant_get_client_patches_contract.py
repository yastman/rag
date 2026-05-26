"""Contract: no anonymous ``patch("telegram_bot.bot.get_client", return_value=MagicMock())``.

Issue #1515 audit, **D5** — `tests/unit/test_bot_handlers.py` accumulated
65+ near-identical ``patch("telegram_bot.bot.get_client", ...)`` calls.
``tests/unit/conftest.py`` already provides an ``autouse=True``
``mock_get_client`` fixture that patches ``telegram_bot.bot.get_client``
with a ``MagicMock()`` whenever ``telegram_bot.bot`` is in ``sys.modules``.
Tests that use the **anonymous** variant — i.e., they do not capture the
patch result and do not need a specific mock instance — are redundant
with the autouse fixture and should rely on it.

This contract test pins that no test file (re)introduces the anonymous
shape ``patch("telegram_bot.bot.get_client", return_value=MagicMock())``
inside a ``with`` / ``patch`` stack. Tests that need to inspect the
returned client (``return_value=mock_lf``, ``return_value=lf``, …) are
**not** flagged: those are legitimate per-test overrides.

The match is a literal substring scan to keep the rule unambiguous and
trivially explainable in PR review. If you genuinely need an anonymous
``MagicMock()`` override, the autouse fixture already gives you one —
remove the inline ``patch`` and let the fixture handle it.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
# The autouse ``mock_get_client`` fixture is defined in
# ``tests/unit/conftest.py``. Only test files under ``tests/unit/`` get
# the fixture, so the redundancy claim is scoped to that subtree.
# Integration / smoke / e2e tests must keep their own explicit patch.
GUARDED_ROOT = TESTS_ROOT / "unit"

# Match the redundant pattern: a literal anonymous MagicMock() / Mock()
# return_value on the bot.get_client patch. Tolerates whitespace around
# the comma but not aliased variables.
REDUNDANT_PATTERN = re.compile(
    r'patch\(\s*["\']telegram_bot\.bot\.get_client["\']\s*,\s*'
    r"return_value\s*=\s*(?:Magic)?Mock\(\)\s*\)"
)


def _python_test_files() -> list[Path]:
    skip = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
    out: list[Path] = []
    for path in GUARDED_ROOT.rglob("*.py"):
        # Only inspect path segments BELOW tests/unit/ — outer worktree
        # paths like ``.worktrees/<branch>/`` are not relevant to the
        # rule and would otherwise cause the entire tree to be skipped
        # under a ``git worktree add`` checkout.
        rel_parts = path.relative_to(GUARDED_ROOT).parts
        if any(part in skip for part in rel_parts):
            continue
        if path.name == Path(__file__).name:  # don't scan ourselves
            continue
        out.append(path)
    return out


def test_no_redundant_anonymous_get_client_patches() -> None:
    offenders: dict[str, int] = {}
    for path in _python_test_files():
        text = path.read_text(encoding="utf-8")
        matches = REDUNDANT_PATTERN.findall(text)
        if matches:
            offenders[str(path.relative_to(REPO_ROOT))] = len(matches)

    if offenders:
        details = "\n  ".join(f"{p}: {n}" for p, n in sorted(offenders.items()))
        raise AssertionError(
            "Anonymous patch('telegram_bot.bot.get_client', "
            "return_value=MagicMock()) calls are redundant with the "
            "autouse mock_get_client fixture in tests/unit/conftest.py "
            "(#1515 audit D5). Drop the inline patch and let the fixture "
            "handle it; if you actually need a specific mock, capture it "
            "into a variable (return_value=mock_lf) so reviewers can see "
            "the dependency.\n  " + details
        )
