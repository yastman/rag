"""Contract: DEPS-8 keeps KFP/Kubernetes out of the root dependency graph.

The Docling HTTP service owns ``docling-serve`` in ``services/docling``.  The
root project talks to that service over HTTP and must not pull Kubeflow
Pipelines or Kubernetes SDK packages into the root lockfile through optional
service dependencies.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = ROOT / "pyproject.toml"
ROOT_LOCK = ROOT / "uv.lock"
FORBIDDEN_ROOT_PACKAGES = {
    "kfp",
    "kfp-kubernetes",
    "kfp-pipeline-spec",
    "kfp-server-api",
    "kubernetes",
}


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _package_names_from_lock(path: Path) -> set[str]:
    data = _load_toml(path)
    return {package["name"] for package in data.get("package", [])}


def _package_name(requirement: str) -> str:
    return requirement.split("[", 1)[0].split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].strip().lower()


def test_root_lock_does_not_include_kfp_or_kubernetes_packages() -> None:
    packages = _package_names_from_lock(ROOT_LOCK)
    assert packages.isdisjoint(FORBIDDEN_ROOT_PACKAGES)


def test_root_docling_extra_does_not_install_docling_serve() -> None:
    optional = _load_toml(ROOT_PYPROJECT)["project"].get("optional-dependencies", {})
    docling_deps = {_package_name(dep) for dep in optional.get("docling", [])}
    assert "docling-serve" not in docling_deps
