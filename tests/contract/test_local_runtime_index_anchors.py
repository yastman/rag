"""Contract: ``docs/indexes/local-runtime.md`` anchors must point at real headings (#1612).

The runtime index links to ``docs/LOCAL-DEVELOPMENT.md`` using GitHub-style
slugified anchors. When section numbers in LOCAL-DEVELOPMENT.md change, the
index links go stale silently. This contract slugifies every ``##`` heading
in LOCAL-DEVELOPMENT.md and asserts that every ``LOCAL-DEVELOPMENT.md#anchor``
link in the runtime index resolves to one of those slugs.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_INDEX = REPO_ROOT / "docs" / "indexes" / "local-runtime.md"
LOCAL_DEV = REPO_ROOT / "docs" / "LOCAL-DEVELOPMENT.md"


_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _github_slugify(heading_text: str) -> str:
    """Approximate GitHub's heading slug algorithm.

    Lowercase, drop characters that are not alphanumeric/hyphen/space, then
    collapse whitespace to single hyphens.
    """
    text = heading_text.lower()
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text


def _collect_anchors(md_text: str) -> set[str]:
    return {_github_slugify(m.group(2)) for m in _HEADING_RE.finditer(md_text)}


def _collect_local_dev_links(index_text: str) -> list[str]:
    """Return every fragment that targets LOCAL-DEVELOPMENT.md."""
    targets = []
    for match in _LINK_RE.finditer(index_text):
        href = match.group(1)
        if "LOCAL-DEVELOPMENT.md#" not in href:
            continue
        # Split on '#' once; we only care about the fragment part.
        fragment = href.split("#", 1)[1]
        targets.append(fragment)
    return targets


def test_runtime_index_local_dev_anchors_resolve() -> None:
    assert RUNTIME_INDEX.exists(), f"missing: {RUNTIME_INDEX}"
    assert LOCAL_DEV.exists(), f"missing: {LOCAL_DEV}"

    anchors = _collect_anchors(LOCAL_DEV.read_text(encoding="utf-8"))
    fragments = _collect_local_dev_links(RUNTIME_INDEX.read_text(encoding="utf-8"))
    assert fragments, "Runtime index must reference at least one LOCAL-DEVELOPMENT.md anchor"

    missing = sorted({frag for frag in fragments if frag not in anchors})
    if missing:
        # Surface a few candidate slugs to make fixing the link obvious.
        candidates = sorted(a for a in anchors if "minimal" in a or "common" in a or "issues" in a)
        raise AssertionError(
            "Runtime index links point to anchors that do not exist in "
            "LOCAL-DEVELOPMENT.md:\n  - "
            + "\n  - ".join(missing)
            + "\nClosest candidate slugs in LOCAL-DEVELOPMENT.md:\n  - "
            + "\n  - ".join(candidates or ["<none>"])
        )


def test_slugify_handles_numbered_section_headings() -> None:
    """Ensure the slug algorithm matches GitHub for the numbered headings used here."""
    assert _github_slugify("8. Minimal Stack (Fast Iteration)") == (
        "8-minimal-stack-fast-iteration"
    )
    assert _github_slugify("11. Common Issues") == "11-common-issues"
    assert _github_slugify("1. Bootstrap Workspace") == "1-bootstrap-workspace"
