"""Dependency split contracts for the core runtime and optional extras (#2484, #2640)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")
MAKEFILE = Path("Makefile")

# Archived extras removed by #2640 (monolith archival epic #2596)
# Note: "eval" was also removed in #2043 (ragas CVE-2026-6587 — dead dep, zero imports)
ARCHIVED_EXTRAS = {"observability", "ui", "mini-app", "voice"}


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
        "datasets",
        "pandas",
        "livekit-agents",
        "gradio",
        "pillow",
        "langfuse",
        "apscheduler",
        "ragas",
    }

    assert expected_core.issubset(base)
    assert base.isdisjoint(forbidden)


def test_optional_extras_cover_platform_surfaces() -> None:
    """Optional extras should make each non-core surface explicit."""
    extras = _project()["project"]["optional-dependencies"]

    assert {"aiogram", "aiogram-dialog", "fluentogram"}.issubset(_dep_names(extras["telegram"]))
    # providers is intentionally empty after #2893 (anthropic/groq removed with dead module)
    assert extras["providers"] == []
    assert {"docling", "fastembed"}.issubset(_dep_names(extras["docling-native"]))
    assert "pymupdf" not in _dep_names(extras["docling-native"])  # removed with document_parser.py


def test_archived_extras_removed_from_pyproject() -> None:
    """Archived surface extras must be removed from pyproject.toml (#2640)."""
    extras = _project()["project"]["optional-dependencies"]
    still_present = ARCHIVED_EXTRAS & set(extras)
    assert not still_present, (
        f"Archived extras still present in pyproject.toml: {sorted(still_present)}. "
        "Remove them as part of #2640 monolith archival."
    )


def test_all_extra_includes_every_kept_runtime_surface() -> None:
    """`uv sync --all-extras` should cover all kept surfaces after archival (#2640)."""
    all_extra = " ".join(_project()["project"]["optional-dependencies"]["all"])

    for name in ["core", "telegram", "providers", "docling-native"]:
        assert name in all_extra, f"'all' extra must include '{name}'"

    for name in ARCHIVED_EXTRAS:
        assert name not in all_extra, (
            f"'all' extra must not include archived extra '{name}' (#2640)"
        )


def test_full_optional_unit_lanes_sync_all_extras() -> None:
    """Full local/CI-style unit lanes must exercise the complete dependency set."""
    text = MAKEFILE.read_text()

    assert "test-unit-full" in text
    assert "test-unit-extras" in text
    assert text.count("uv sync --all-extras --all-groups") >= 2
