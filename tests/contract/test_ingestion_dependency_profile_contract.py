"""Contract for the LiteLLM-free Markdown ingestion dependency profile."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = ROOT / "pyproject.toml"
ROOT_LOCK = ROOT / "uv.lock"
BGE_PYPROJECT = ROOT / "services" / "bge-m3-api" / "pyproject.toml"
BGE_LOCK = ROOT / "services" / "bge-m3-api" / "uv.lock"


def _project(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def _names(dependencies: list[str]) -> set[str]:
    return {
        re.match(r"[A-Za-z0-9_.-]+", dependency).group(0).lower().replace("_", "-")
        for dependency in dependencies
    }


def _lock_names(path: Path) -> set[str]:
    return {
        package["name"]
        for package in tomllib.loads(path.read_text(encoding="utf-8")).get("package", [])
    }


def test_ingestion_profile_is_litellm_free_and_markdown_complete() -> None:
    project = _project(ROOT_PYPROJECT)
    extras = project["optional-dependencies"]
    ingestion = _names(project["dependencies"]) | _names(extras["docling-native"])

    assert "litellm" not in ingestion
    assert "docling" not in ingestion
    assert "fastembed" not in ingestion
    assert {"docling-slim", "docling-core", "qdrant-client"} <= ingestion
    assert "docling-slim[format-markdown,feat-chunking]==2.115.0" in extras["docling-native"]
    assert "docling-core[chunking]==2.87.1" in extras["docling-native"]
    assert "scipy==1.18.0" in extras["docling-native"]
    assert "pypdfium2==5.11.0" in extras["docling-native"]
    assert "docling-parse==7.5.0" in extras["docling-native"]
    assert "rtree==1.4.1" in extras["docling-native"]
    assert "docling-ibm-models==3.13.3" in extras["docling-native"]


def test_deferred_api_extra_retains_litellm_pin() -> None:
    extras = _project(ROOT_PYPROJECT)["optional-dependencies"]
    assert extras["api"] == ["litellm==1.93.0"]


def test_ingestion_lock_excludes_full_docling_and_fastembed() -> None:
    names = _lock_names(ROOT_LOCK)
    assert {"docling", "fastembed"}.isdisjoint(names)
    assert {"docling-slim", "docling-core", "qdrant-client"} <= names


def test_bge_service_does_not_declare_or_lock_scipy() -> None:
    assert "scipy" not in _names(_project(BGE_PYPROJECT)["dependencies"])
    assert "scipy" not in _lock_names(BGE_LOCK)
