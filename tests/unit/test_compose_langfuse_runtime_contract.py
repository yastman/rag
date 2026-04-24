"""Regression tests for the Langfuse compose runtime contract (#1080)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "compose.yml"
COMPOSE_CI_ENV = ROOT / "tests" / "fixtures" / "compose.ci.env"

LANGFUSE_SERVICES = ("langfuse-worker", "langfuse")
STATEFUL_DEPS = ("postgres", "clickhouse", "minio", "redis-langfuse")


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def _render_vps_ml_compose() -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if key == "PATH" or key.startswith("DOCKER_")
    }
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(COMPOSE_CI_ENV),
            "-f",
            "compose.yml",
            "-f",
            "compose.vps.yml",
            "--profile",
            "ml",
            "--compatibility",
            "config",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return yaml.safe_load(rendered.stdout)


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


@pytest.fixture(scope="module")
def vps_ml_compose() -> dict:
    return _render_vps_ml_compose()


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

    def test_vps_clickhouse_password_matches_langfuse_clients(self, vps_ml_compose: dict) -> None:
        services = vps_ml_compose["services"]
        clickhouse_password = services["clickhouse"]["environment"]["CLICKHOUSE_PASSWORD"]

        assert clickhouse_password, "VPS clickhouse.CLICKHOUSE_PASSWORD must not render empty"
        for service in LANGFUSE_SERVICES:
            assert services[service]["environment"]["CLICKHOUSE_PASSWORD"] == clickhouse_password

    def test_vps_minio_secret_is_required_for_langfuse_s3(self, vps_ml_compose: dict) -> None:
        services = vps_ml_compose["services"]
        minio_password = services["minio"]["environment"]["MINIO_ROOT_PASSWORD"]

        assert minio_password, "VPS minio.MINIO_ROOT_PASSWORD must not render empty"
        for service in LANGFUSE_SERVICES:
            env = services[service]["environment"]
            assert env["LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY"] == minio_password
            assert env["LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY"] == minio_password
