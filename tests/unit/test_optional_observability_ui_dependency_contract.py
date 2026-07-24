"""Contracts for archived observability/heavy UI dependencies (#2431, #2640)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")
# These packages must NOT appear in base deps or dev group after archival (#2640)
ARCHIVED_PACKAGES = {"gradio", "pillow", "langfuse"}


def _dep_names(deps: list[str]) -> set[str]:
    names: set[str] = set()
    for dep in deps:
        match = re.match(r"([A-Za-z0-9_.-]+)", dep)
        assert match, f"Could not parse dependency {dep!r}"
        names.add(match.group(1).lower().replace("_", "-"))
    return names


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_observability_and_heavy_ui_are_not_base_dependencies() -> None:
    base = _dep_names(_project()["project"]["dependencies"])

    assert base.isdisjoint(ARCHIVED_PACKAGES)


def test_archived_packages_not_in_dev_group() -> None:
    """langfuse, gradio, pillow must be removed from dev group after archival (#2640)."""
    dev_deps = _project().get("dependency-groups", {}).get("dev", [])
    dev_dep_names = _dep_names([d for d in dev_deps if isinstance(d, str)])
    still_present = ARCHIVED_PACKAGES & dev_dep_names
    assert not still_present, (
        f"Archived packages still in [dependency-groups.dev]: {sorted(still_present)}. "
        "Remove them as part of #2640."
    )
