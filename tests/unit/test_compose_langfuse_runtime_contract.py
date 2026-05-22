"""Regression tests for the Langfuse compose runtime contract (#1080)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "compose.yml"

LANGFUSE_SERVICES = ("langfuse-worker", "langfuse")
STATEFUL_DEPS = ("postgres", "clickhouse", "minio", "redis-langfuse")


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def _depends_on(compose: dict, service: str, dependency: str) -> dict:
    svc = compose["services"][service]
    depends = svc.get("depends_on")
    assert isinstance(depends, dict), f"{service}.depends_on must use long syntax"
    assert dependency in depends, f"{service}.depends_on is missing {dependency}"

    dep = depends[dependency]
    assert isinstance(dep, dict), f"{service}.depends_on.{dependency} must use long syntax"
    return dep


@pytest.fixture(scope="module")
def compose() -> dict:
    return _load_compose()


class TestLangfuseRuntimeContract:
    """Langfuse services must restart cleanly after dependent stateful services recreate."""

    @pytest.mark.parametrize("service", LANGFUSE_SERVICES)
    def test_restart_propagation_is_limited_to_stateful_dependencies(
        self,
        compose: dict,
        service: str,
    ) -> None:
        depends = compose["services"][service]["depends_on"]
        assert isinstance(depends, dict), f"{service}.depends_on must use long syntax"

        restart_enabled = {
            dependency
            for dependency, config in depends.items()
            if isinstance(config, dict) and config.get("restart") is True
        }
        assert restart_enabled == set(STATEFUL_DEPS), (
            f"{service}.depends_on restart propagation must be limited to {STATEFUL_DEPS}, "
            f"got {sorted(restart_enabled)}"
        )

    @pytest.mark.parametrize("service", LANGFUSE_SERVICES)
    @pytest.mark.parametrize("dependency", STATEFUL_DEPS)
    def test_stateful_dependencies_are_healthy_and_restart_propagates(
        self,
        compose: dict,
        service: str,
        dependency: str,
    ) -> None:
        dep = _depends_on(compose, service, dependency)
        assert dep.get("condition") == "service_healthy", (
            f"{service}.depends_on.{dependency} must wait for service_healthy"
        )
        assert dep.get("restart") is True, (
            f"{service}.depends_on.{dependency} must set restart: true to follow dependency recreation"
        )

    def test_web_depends_on_worker_without_restart_propagation(self, compose: dict) -> None:
        dep = _depends_on(compose, "langfuse", "langfuse-worker")
        assert dep.get("condition") == "service_started", (
            "langfuse.depends_on.langfuse-worker must use condition: service_started"
        )
        assert dep.get("restart") is not True, (
            "langfuse.depends_on.langfuse-worker must not set restart: true"
        )
