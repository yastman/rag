"""Dependency split contracts for the core runtime and optional extras (#2484)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")
MAKEFILE = Path("Makefile")


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def _dep_names(deps: list[str]) -> set[str]:
    names: set[str] = set()
    for dep in deps:
        match = re.match(r"([A-Za-z0-9_.-]+)", dep)
        assert match, f"Could not parse dependency name from {dep!r}"
        names.add(match.group(1).lower().replace("_", "-"))
    return names


def test_base_dependencies_are_core_only() -> None:
    """Heavy adapters should not be installed by the default runtime install."""
    base = _dep_names(_project()["project"]["dependencies"])

    expected_core = {
        "litellm",
        "openai",
        "qdrant-client",
        "redis",
        "redisvl",
        "pydantic-settings",
        "httpx",
        "tenacity",
        "pyyaml",
    }
    forbidden = {
        "aiogram",
        "aiogram-dialog",
        "fluentogram",
        "anthropic",
        "groq",
        "instructor",
        "docling",
        "cocoindex",
        "fastembed",
        "ragas",
        "datasets",
        "pandas",
        "livekit-agents",
        "gradio",
        "pillow",
        "langfuse",
        "apscheduler",
    }

    assert expected_core.issubset(base)
    assert base.isdisjoint(forbidden)


def test_optional_extras_cover_platform_surfaces() -> None:
    """Optional extras should make each non-core surface explicit."""
    extras = _project()["project"]["optional-dependencies"]

    assert {"aiogram", "aiogram-dialog", "fluentogram"}.issubset(_dep_names(extras["telegram"]))
    assert {"anthropic", "groq"}.issubset(_dep_names(extras["providers"]))
    assert "instructor" not in _dep_names(extras["providers"])
    assert {"docling", "cocoindex", "pymupdf", "fastembed"}.issubset(
        _dep_names(extras["ingestion"])
    )
    assert {"datasets", "pandas"}.issubset(_dep_names(extras["eval"]))
    assert "ragas" not in _dep_names(extras["eval"])
    # voice extra emptied by ARCH-02 #2598 (livekit-* archived to archive/voice/)
    assert "voice" in extras


def test_all_extra_includes_every_runtime_surface() -> None:
    """`uv sync --all-extras` should preserve the historical full install."""
    all_extra = " ".join(_project()["project"]["optional-dependencies"]["all"])

    for name in [
        "core",
        "telegram",
        "providers",
        "observability",
        "ingest",
        "eval",
        "voice",
        "ui",
    ]:
        assert name in all_extra


def test_full_optional_unit_lanes_sync_all_extras() -> None:
    """Full local/CI-style unit lanes must exercise the complete dependency set."""
    text = MAKEFILE.read_text()

    assert "test-unit-full" in text
    assert "test-unit-extras" in text
    assert text.count("uv sync --all-extras --all-groups") >= 2
