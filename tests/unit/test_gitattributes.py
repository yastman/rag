"""Repository line-ending policy contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_gitattributes_pins_text_line_endings() -> None:
    text = (ROOT / ".gitattributes").read_text()

    for expected in [
        "* text=auto",
        "*.py text eol=lf",
        "*.sh text eol=lf",
        "*.yaml text eol=lf",
        "*.yml text eol=lf",
        "*.toml text eol=lf",
        "*.md text eol=lf",
    ]:
        assert expected in text
