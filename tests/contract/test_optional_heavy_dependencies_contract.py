"""Contract: DEPS-7 keeps heavy/observability packages out of base deps."""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = ROOT / "pyproject.toml"
TELEGRAM_PYPROJECT = ROOT / "telegram_bot" / "pyproject.toml"
OPTIONAL_PACKAGES = {
    "gradio",
    "pillow",
    "langfuse",
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


def test_root_base_dependencies_exclude_optional_heavy_packages() -> None:
    deps = {_package_name(dep) for dep in _load(ROOT_PYPROJECT)["project"]["dependencies"]}
    assert deps.isdisjoint(OPTIONAL_PACKAGES)


def test_telegram_base_dependencies_exclude_optional_heavy_packages() -> None:
    deps = {_package_name(dep) for dep in _load(TELEGRAM_PYPROJECT)["project"]["dependencies"]}
    assert deps.isdisjoint(OPTIONAL_PACKAGES)


def test_root_extras_keep_optional_dependency_targets() -> None:
    optional = _load(ROOT_PYPROJECT)["project"].get("optional-dependencies", {})
    flattened = {_package_name(dep) for deps in optional.values() for dep in deps}
    assert flattened >= OPTIONAL_PACKAGES


def test_telegram_extras_keep_observability_targets() -> None:
    optional = _load(TELEGRAM_PYPROJECT)["project"].get("optional-dependencies", {})
    flattened = {_package_name(dep) for deps in optional.values() for dep in deps}
    assert {"langfuse"} <= flattened
