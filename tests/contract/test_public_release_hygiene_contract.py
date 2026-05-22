"""Public release hygiene contract (#1565).

Pins the public-release cleanup intent of issue #1565 into the test suite so
regressions are caught at PR time rather than at release time.

Scope (all derived from the #1565 checklist):

- ``.gitignore`` must encode the public-release patterns (Telethon sessions,
  internal AI/agent artifacts, source documents).
- ``.gitignore`` must keep ``docs/reports/README.md`` trackable so the
  reports directory remains discoverable for operators.
- No tracked file may match the public-release blacklist (Telethon
  ``*.session`` files, ``docs/documents/*.docx``/``*.pdf`` source documents,
  ``docs/audits/`` internal audit reports).
- ``tests/fixtures/compose.ci.env`` may only contain test/dummy values, not
  values that look like production tokens.

These assertions are intentionally conservative; they encode behaviour that
already holds on ``dev`` so any future change that breaks the public-release
posture surfaces in CI as a contract failure.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _gitignore_lines() -> list[str]:
    return (REPO_ROOT / ".gitignore").read_text().splitlines()


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True)
    return out.splitlines()


# ---------------------------------------------------------------------------
# .gitignore patterns required by #1565
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        "*.session",  # Telethon session files (E2E auth tokens)
        "*.session-journal",  # Telethon session companions
        "docs/audits/",  # internal audit reports
        "docs/archive/",  # archived internal documents
        "docs/superpowers/",  # internal AI/agent tooling
    ],
)
def test_gitignore_contains_public_release_pattern(pattern: str) -> None:
    """Each public-release pattern from #1565 must remain in ``.gitignore``."""
    lines = _gitignore_lines()
    assert pattern in lines, (
        f"Public-release hygiene regression (#1565): pattern {pattern!r} "
        f"missing from .gitignore. Restore it before merging."
    )


def test_gitignore_keeps_docs_reports_readme_trackable() -> None:
    """``docs/reports/README.md`` must remain trackable per #1565.

    Issue #1565 calls for ``docs/reports/`` to be ignored *except* for the
    README. The current ``.gitignore`` has ``docs/reports/*`` (which excludes
    everything, including README.md) without the matching
    ``!docs/reports/README.md`` exception. This test pins the contract: if
    ``docs/reports/*`` is present, the README.md exception must accompany it.
    """
    lines = _gitignore_lines()
    excludes_all = "docs/reports/*" in lines
    has_readme_exception = "!docs/reports/README.md" in lines
    if excludes_all:
        assert has_readme_exception, (
            "docs/reports/* in .gitignore excludes README.md too. "
            "Per #1565, README.md must remain trackable so the reports "
            "directory stays discoverable. Add `!docs/reports/README.md` "
            "AFTER the `docs/reports/*` line."
        )


# ---------------------------------------------------------------------------
# Blacklist: tracked files that must never appear post-cleanup
# ---------------------------------------------------------------------------


def test_no_tracked_telethon_session_files() -> None:
    """No ``*.session`` file may be tracked (Telethon auth tokens)."""
    bad = [f for f in _tracked_files() if f.endswith(".session")]
    assert bad == [], (
        f"Telethon session files leaked into git (#1565): {bad}. "
        f"Run `git rm` and ensure `*.session` is in .gitignore."
    )


def test_no_tracked_unrelated_office_documents() -> None:
    """``docs/documents/`` must contain only README/docs, not raw .docx/.pdf."""
    bad = [
        f
        for f in _tracked_files()
        if f.startswith("docs/documents/") and f.lower().endswith((".docx", ".pdf"))
    ]
    assert bad == [], (
        f"Unrelated source documents tracked under docs/documents/ "
        f"(#1565): {bad}. Move these to data/ or remove them."
    )


def test_no_tracked_files_under_internal_audit_paths() -> None:
    """``docs/audits/`` and ``docs/archive/`` must stay empty in git."""
    bad = [f for f in _tracked_files() if f.startswith(("docs/audits/", "docs/archive/"))]
    assert bad == [], (
        f"Internal audit/archive files tracked (#1565): {bad}. "
        f"These directories are ignored for the public release; remove "
        f"committed copies."
    )


# ---------------------------------------------------------------------------
# Test fixture env file must stay dummy-only
# ---------------------------------------------------------------------------


# Patterns that look like real credentials (not the test placeholders the
# fixture is supposed to contain). We accept anything that explicitly
# advertises itself as a placeholder via the words ``test``, ``dummy``,
# ``placeholder``, ``example``, or all-zero/all-same hex.
_PRODUCTION_LOOKING_VALUE = re.compile(
    r"^(?!.*(test|dummy|placeholder|example|fake|local))"  # not a placeholder
    r"(?!0+$)(?!([0-9a-f])\1+$)"  # not all-same hex
    r"[A-Za-z0-9_\-]{32,}$"  # long opaque token
)


def test_compose_ci_env_only_contains_dummy_values() -> None:
    """``tests/fixtures/compose.ci.env`` must never contain real secrets.

    Per #1565 audit step: "Verify this file only contains test/dummy values
    and never had real secrets committed." We scan each ``KEY=VALUE`` line
    for values that look like production credentials (long opaque tokens
    that do not advertise themselves as a placeholder).
    """
    fixture = REPO_ROOT / "tests" / "fixtures" / "compose.ci.env"
    if not fixture.exists():
        pytest.skip("compose.ci.env fixture not present in this checkout")

    suspicious: list[tuple[str, str]] = []
    for raw in fixture.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Strip optional inline comments / quoting.
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if _PRODUCTION_LOOKING_VALUE.match(value):
            suspicious.append((key, value[:8] + "…"))

    assert suspicious == [], (
        f"compose.ci.env contains values that look like production "
        f"credentials (#1565 audit): {suspicious}. Replace each with a "
        f"placeholder string containing 'test', 'dummy', 'placeholder', "
        f"'example', 'fake', or 'local'."
    )
