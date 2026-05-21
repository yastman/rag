"""Contract tests for GitHub Actions versions used in CI workflows (issue #1338).

The workflows pin actions by SHA + version comment. PR #1319 bumped them to
``actions/checkout@v6`` and ``astral-sh/setup-uv@v8``. ``v6`` of checkout
specifically requires Actions Runner v2.329.0+, which is a hard prerequisite
for the self-hosted runner used by ``nightly-heavy.yml``.

These tests guard the contract so a future SHA bump cannot accidentally
downgrade the major version (e.g. back to ``checkout@v5``) and silently
break the self-hosted runner pipeline. The tests also enforce that every
workflow's pinned version comment matches the documented requirement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Issue #1338 contract — minimum required versions of GitHub Actions used by
# any workflow. The values match the Actions Runner v2.329.0+ floor.
MIN_VERSIONS: dict[str, int] = {
    "actions/checkout": 6,
    "astral-sh/setup-uv": 8,
}

# Self-hosted runners must be at least this version for `actions/checkout@v6`
# (Node 24 runtimes). Documented here so a bump in either side is reviewable.
MIN_SELF_HOSTED_RUNNER_VERSION = "2.329.0"


def _workflow_files() -> list[Path]:
    assert WORKFLOWS_DIR.exists(), f"{WORKFLOWS_DIR} must exist"
    files = sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))
    assert files, "Expected at least one workflow file under .github/workflows/"
    return files


def _extract_action_versions(workflow_text: str) -> list[tuple[str, str]]:
    """Return (action, version) pairs from ``uses: action@sha # vX.Y`` lines.

    Pinned actions follow the convention::

        uses: actions/checkout@<sha> # v6

    The version comment is the source of truth; the SHA is opaque.
    """
    pattern = re.compile(
        r"uses:\s+([\w./-]+)@[a-f0-9]{7,40}\s*#\s*v?([\d.]+)",
    )
    return pattern.findall(workflow_text)


@pytest.mark.parametrize("workflow_path", _workflow_files(), ids=lambda p: p.name)
def test_workflow_pins_meet_min_versions(workflow_path: Path) -> None:
    """Each ``uses:`` pin must satisfy ``MIN_VERSIONS`` for tracked actions."""
    text = workflow_path.read_text(encoding="utf-8")
    refs = _extract_action_versions(text)

    violations: list[str] = []
    for action, version in refs:
        if action not in MIN_VERSIONS:
            continue
        major = int(version.split(".")[0])
        if major < MIN_VERSIONS[action]:
            violations.append(f"{action}@v{version} (need v{MIN_VERSIONS[action]}+)")

    assert not violations, (
        f"{workflow_path.name}: action version regression detected — issue "
        f"#1338 requires the listed minimums.\n  Violations: {violations!r}"
    )


def test_nightly_heavy_uses_self_hosted_runner_with_min_version_documented() -> None:
    """``nightly-heavy.yml`` runs on self-hosted; the version floor must be
    documented near ``runs-on: self-hosted`` so future maintainers see it."""
    nightly = WORKFLOWS_DIR / "nightly-heavy.yml"
    assert nightly.exists()
    text = nightly.read_text(encoding="utf-8")
    assert "self-hosted" in text, (
        "nightly-heavy.yml is expected to target self-hosted runners; the "
        "self-hosted version floor only matters there."
    )
    assert MIN_SELF_HOSTED_RUNNER_VERSION in text, (
        f"nightly-heavy.yml must reference the minimum runner version "
        f"({MIN_SELF_HOSTED_RUNNER_VERSION}) in a comment near `runs-on: "
        "self-hosted` so anyone editing the workflow sees the constraint "
        "(issue #1338)."
    )


def test_all_pinned_actions_use_sha_lock() -> None:
    """Defensive guard: every ``uses:`` reference must pin to a SHA, not a
    floating tag, so the version comment we test above is meaningful."""
    pattern = re.compile(r"uses:\s+([\w./-]+)@(\S+)")
    floating: list[str] = []
    for workflow_path in _workflow_files():
        text = workflow_path.read_text(encoding="utf-8")
        for action, ref in pattern.findall(text):
            # Skip relative re-uses of local actions (./.github/actions/foo).
            if action.startswith("./"):
                continue
            # SHA pins are 40-char hex (or 7-char short form) — anything else
            # is a tag/branch reference.
            if not re.fullmatch(r"[a-f0-9]{7,40}", ref):
                floating.append(f"{workflow_path.name}: {action}@{ref}")
    assert not floating, (
        "Every external GitHub Action reference must pin a commit SHA so the "
        f"version comment is auditable. Found floating pins: {floating!r}"
    )
