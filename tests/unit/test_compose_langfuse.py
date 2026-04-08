"""Verify all traced services have LANGFUSE env vars with dev defaults (#langfuse-coverage)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
DEV_COMPOSE = ROOT / "compose.dev.yml"


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _get_service_env(compose: dict, service: str) -> dict[str, str]:
    """Extract environment dict from a compose service."""
    svc = compose["services"][service]
    env = svc.get("environment", {})
    if isinstance(env, list):
        return {
            item.split("=", 1)[0]: (item.split("=", 1)[1] if "=" in item else "") for item in env
        }
    return env


# Сервисы которые ДОЛЖНЫ иметь LANGFUSE vars
TRACED_SERVICES = ["bot", "litellm", "rag-api", "voice-agent", "ingestion"]

# Минимальный набор vars для трейсинга
REQUIRED_LANGFUSE_VARS = [
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
]


@pytest.fixture(scope="module")
def compose_base() -> dict:
    return _load_compose(BASE_COMPOSE)


@pytest.fixture(scope="module")
def compose_dev() -> dict:
    return _load_compose(DEV_COMPOSE)


class TestLangfuseEnvVarsPresent:
    """All traced services must declare LANGFUSE_PUBLIC_KEY, SECRET_KEY, HOST."""

    @pytest.mark.parametrize("service", TRACED_SERVICES)
    @pytest.mark.parametrize("var", REQUIRED_LANGFUSE_VARS)
    def test_service_has_langfuse_var(self, compose_base: dict, service: str, var: str):
        env = _get_service_env(compose_base, service)
        assert var in env, f"compose.yml: {service} missing {var} in environment block"


SERVICES_WITH_DEV_DEFAULTS = ["bot", "litellm", "rag-api", "voice-agent", "ingestion"]


class TestLangfuseSecretPosture:
    """Base compose avoids predictable secrets; dev compose restores convenience defaults."""

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_base_compose_has_no_dev_public_key_default(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_PUBLIC_KEY", ""))
        assert "pk-lf-dev" not in val, (
            f"compose.yml: {service}.LANGFUSE_PUBLIC_KEY must not hardcode dev defaults, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_base_compose_has_no_dev_secret_key_default(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_SECRET_KEY", ""))
        assert "sk-lf-dev" not in val, (
            f"compose.yml: {service}.LANGFUSE_SECRET_KEY must not hardcode dev defaults, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_dev_compose_restores_public_key_default(self, compose_dev: dict, service: str):
        env = _get_service_env(compose_dev, service)
        val = str(env.get("LANGFUSE_PUBLIC_KEY", ""))
        assert "pk-lf-dev" in val, (
            f"compose.dev.yml: {service}.LANGFUSE_PUBLIC_KEY must provide dev default, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_dev_compose_restores_secret_key_default(self, compose_dev: dict, service: str):
        env = _get_service_env(compose_dev, service)
        val = str(env.get("LANGFUSE_SECRET_KEY", ""))
        assert "sk-lf-dev" in val, (
            f"compose.dev.yml: {service}.LANGFUSE_SECRET_KEY must provide dev default, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_host_has_docker_default(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_HOST", ""))
        assert "langfuse:3000" in val, (
            f"compose.yml: {service}.LANGFUSE_HOST must default to http://langfuse:3000, "
            f"got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_base_compose_uses_docker_specific_host_var(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_HOST", ""))
        assert "LANGFUSE_DOCKER_HOST" in val, (
            f"compose.yml: {service}.LANGFUSE_HOST must use LANGFUSE_DOCKER_HOST to avoid "
            f"host localhost values leaking into containers, got: {val!r}"
        )


class TestLitellmCallbacks:
    """LiteLLM config must have langfuse callbacks configured."""

    def test_success_callback_configured(self):
        config_path = ROOT / "docker" / "litellm" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        settings = config.get("litellm_settings", {})
        callbacks = settings.get("success_callback", [])
        assert "langfuse" in callbacks, (
            "docker/litellm/config.yaml: litellm_settings.success_callback must include 'langfuse'"
        )

    def test_failure_callback_configured(self):
        config_path = ROOT / "docker" / "litellm" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        settings = config.get("litellm_settings", {})
        callbacks = settings.get("failure_callback", [])
        assert "langfuse" in callbacks, (
            "docker/litellm/config.yaml: litellm_settings.failure_callback must include 'langfuse'"
        )
