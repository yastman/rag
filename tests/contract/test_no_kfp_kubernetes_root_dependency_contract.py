"""Contract: DEPS-8 keeps KFP/Kubernetes out of the root dependency graph.

The root project must not pull Kubeflow Pipelines or Kubernetes SDK packages
into the root lockfile through optional service dependencies. The Docling
extras that once motivated the ``docling-serve`` guard were removed entirely
by #3235 (Markdown-only ingestion); the lock-level guard below remains as the
regression barrier.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_LOCK = ROOT / "uv.lock"
FORBIDDEN_ROOT_PACKAGES = {
    "kfp",
    "kfp-kubernetes",
    "kfp-pipeline-spec",
    "kfp-server-api",
    "kubernetes",
    # docling-serve must never return via any surface (#3235).
    "docling-serve",
}


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _package_names_from_lock(path: Path) -> set[str]:
    data = _load_toml(path)
    return {package["name"] for package in data.get("package", [])}


def test_root_lock_does_not_include_kfp_or_kubernetes_packages() -> None:
    packages = _package_names_from_lock(ROOT_LOCK)
    assert packages.isdisjoint(FORBIDDEN_ROOT_PACKAGES)
