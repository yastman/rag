"""Dependency split contracts for the core runtime and optional extras (#2484, #2640, #3335)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")
MAKEFILE = Path("Makefile")

# Archived extras removed by #2640 (monolith archival epic #2596)
# Note: "eval" was also removed in #2043 (ragas CVE-2026-6587 — dead dep, zero imports)
ARCHIVED_EXTRAS = {"observability", "providers", "ui", "mini-app", "voice"}


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
    """Heavy adapters should not be installed by the default runtime install.

    #3365: the Redis client cohort (redis-py, RedisVL) left the base
    dependencies for the explicit ``redis`` extra — base declares no Redis
    package; the Redis-enabled Telegram image opts in via
    ``--extra telegram --extra redis``.
    """
    project = _project()
    base = _dep_names(project["project"]["dependencies"])

    expected_core = {
        "litellm",
        "openai",
        "qdrant-client",
        "pydantic-settings",
        "httpx",
        "tenacity",
        "pyyaml",
    }
    forbidden = {
        "aiogram",
        "aiogram-dialog",
        "fluentogram",
        "redis",
        "redisvl",
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

    # #3365: the redis extra is the single authority for the client cohort.
    extras = project["project"]["optional-dependencies"]
    assert {"redis", "redisvl"}.issubset(_dep_names(extras["redis"]))


def test_optional_extras_cover_platform_surfaces() -> None:
    """Optional extras should make each non-core surface explicit."""
    extras = _project()["project"]["optional-dependencies"]

    assert {"aiogram", "aiogram-dialog", "fluentogram"}.issubset(_dep_names(extras["telegram"]))
    # docling-native was removed by #3235: ingestion is Markdown-only stdlib.
    assert "docling-native" not in extras
    assert "pymupdf" not in _dep_names(extras.get("bge-extras", []))


def test_archived_extras_removed_from_pyproject() -> None:
    """Archived surface extras must be removed from pyproject.toml (#2640)."""
    extras = _project()["project"]["optional-dependencies"]
    still_present = ARCHIVED_EXTRAS & set(extras)
    assert not still_present, (
        f"Archived extras still present in pyproject.toml: {sorted(still_present)}. "
        "Remove them as part of #2640 monolith archival."
    )


def test_core_and_all_extras_removed() -> None:
    """The redundant `core` and `all` extras must stay removed (#3335).

    Plain base dependencies are the core authority and `uv sync` installs them;
    lanes select `telegram` or `bge-extras` directly. `uv sync --all-extras`
    (uv CLI flag used by Makefile lanes) keeps working over the kept extras.
    """
    extras = _project()["project"]["optional-dependencies"]

    assert "core" not in extras, (
        "The `core` extra duplicated the base dependencies; plain base is the "
        "core authority (#3335)."
    )
    assert "all" not in extras, (
        "The uncalled `all` umbrella extra was removed by #3335; select "
        "`telegram` or `bge-extras` directly instead."
    )


def test_extras_do_not_duplicate_base_dependencies() -> None:
    """Extras must add only new packages, never re-declare base ones (#3335)."""
    project = _project()
    base = _dep_names(project["project"]["dependencies"])
    extras = project["project"]["optional-dependencies"]

    for name, deps in extras.items():
        overlap = _dep_names(deps) & base
        assert not overlap, (
            f"Extra '{name}' re-declares base dependencies: {sorted(overlap)}. "
            "Base is the single authority for those packages (#3335)."
        )


def test_full_optional_unit_lanes_sync_all_extras() -> None:
    """Full local/CI-style unit lanes must exercise the complete dependency set."""
    text = MAKEFILE.read_text()

    assert "test-unit-full" in text
    assert "test-unit-extras" in text
    assert text.count("uv sync --all-extras --all-groups") >= 2
