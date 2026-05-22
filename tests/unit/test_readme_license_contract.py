"""Static contract tests for README.md and LICENSE consistency."""

import re
from pathlib import Path


README = Path("README.md")
LICENSE = Path("LICENSE")


def test_license_file_exists() -> None:
    assert LICENSE.is_file(), "LICENSE file must exist"


def test_license_is_mit() -> None:
    text = LICENSE.read_text(encoding="utf-8")
    assert "MIT License" in text, "LICENSE must declare MIT License"
    assert "Permission is hereby granted" in text, "LICENSE must contain MIT permission text"


def test_readme_links_to_license() -> None:
    text = README.read_text(encoding="utf-8")
    assert "[MIT License](LICENSE)" in text, "README must link to LICENSE via MIT License anchor"


def test_readme_does_not_use_brittle_node_count() -> None:
    text = README.read_text(encoding="utf-8")
    # Exact parenthetical node counts like "(11 nodes)" are brittle because
    # the graph node count varies by configuration (guard and summarize are
    # conditional). We allow descriptive adjectives but not exact counts.
    match = re.search(r"\(\d+\s+nodes?\)", text)
    assert match is None, (
        f"README must not contain brittle exact node counts like {match.group(0)!r}; "
        "use non-fragile wording instead"
    )
