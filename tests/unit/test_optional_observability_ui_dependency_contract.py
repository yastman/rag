"""Contracts for optional observability/heavy UI dependencies (#2431)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml


PYPROJECT = Path("pyproject.toml")
COMPOSE_DEV = Path("compose.dev.yml")
HEAVY_OPTIONAL = {"gradio", "pillow", "sentry-sdk", "langfuse"}


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

    assert base.isdisjoint(HEAVY_OPTIONAL)


def test_observability_scheduling_and_ui_extras_own_heavy_deps() -> None:
    extras = _project()["project"]["optional-dependencies"]

    assert {"langfuse", "sentry-sdk"}.issubset(_dep_names(extras["observability"]))
    assert {"pillow", "gradio"}.issubset(_dep_names(extras["ui"]))
    # apscheduler/scheduling extra removed in #2602


def test_langfuse_self_host_services_stay_profile_gated() -> None:
    compose = yaml.safe_load(COMPOSE_DEV.read_text())
    services = compose["services"]
    langfuse_stack = {"clickhouse", "minio", "redis-langfuse", "langfuse-worker", "langfuse"}

    for service_name in langfuse_stack:
        profiles = set(services[service_name].get("profiles", []))
        assert "ml" in profiles, f"{service_name} must stay behind the ml profile"
