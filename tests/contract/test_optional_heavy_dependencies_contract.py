"""Contract: DEPS-7 keeps archived heavy packages out of root dependency lanes (#2640)."""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = ROOT / "pyproject.toml"
TELEGRAM_PYPROJECT = ROOT / "telegram_bot" / "pyproject.toml"
# Archived UI/observability packages: absent from base, dev, and optional lanes (#2640).
ARCHIVED_PACKAGES = {
    "gradio",
    "pillow",
    "langfuse",
    "uvicorn",
}


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _package_name(requirement: str) -> str:
    return (
        requirement.split("[", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .strip()
        .lower()
    )


def test_root_base_dependencies_exclude_archived_packages() -> None:
    deps = {_package_name(dep) for dep in _load(ROOT_PYPROJECT)["project"]["dependencies"]}
    assert deps.isdisjoint(ARCHIVED_PACKAGES)


def test_telegram_base_dependencies_exclude_archived_packages() -> None:
    deps = {_package_name(dep) for dep in _load(TELEGRAM_PYPROJECT)["project"]["dependencies"]}
    assert deps.isdisjoint(ARCHIVED_PACKAGES)


def test_root_dev_group_excludes_archived_packages() -> None:
    """Dev group must not pull archived-surface packages into the dev install (#2640)."""
    dev_deps = _load(ROOT_PYPROJECT).get("dependency-groups", {}).get("dev", [])
    dev_names = {_package_name(d) for d in dev_deps if isinstance(d, str)}
    still_present = ARCHIVED_PACKAGES & dev_names
    assert not still_present, (
        f"Archived packages still in [dependency-groups.dev]: {sorted(still_present)}"
    )


def test_root_extras_do_not_contain_archived_packages() -> None:
    """Archived UI/observability extras must stay removed from pyproject.toml (#2640)."""
    optional = _load(ROOT_PYPROJECT)["project"].get("optional-dependencies", {})
    flattened = {_package_name(dep) for deps in optional.values() for dep in deps}
    still_present = ARCHIVED_PACKAGES & flattened
    assert not still_present, (
        f"Archived packages still referenced in optional extras: {sorted(still_present)}"
    )
