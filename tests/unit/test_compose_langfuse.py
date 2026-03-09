"""Verify all traced services have LANGFUSE env vars with dev defaults (#langfuse-coverage)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"


def _load_compose() -> dict:
    return yaml.safe_load(BASE_COMPOSE.read_text())


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
def compose() -> dict:
    return _load_compose()


class TestLangfuseEnvVarsPresent:
    """All traced services must declare LANGFUSE_PUBLIC_KEY, SECRET_KEY, HOST."""

    @pytest.mark.parametrize("service", TRACED_SERVICES)
    @pytest.mark.parametrize("var", REQUIRED_LANGFUSE_VARS)
    def test_service_has_langfuse_var(self, compose: dict, service: str, var: str):
        env = _get_service_env(compose, service)
        assert var in env, f"compose.yml: {service} missing {var} in environment block"


# Сервисы где дефолт ДОЛЖЕН быть непустым (dev-ready)
SERVICES_WITH_DEV_DEFAULTS = ["bot", "litellm", "rag-api", "voice-agent", "ingestion"]

# Паттерн для пустого дефолта: ${VAR:-} или ${VAR:-""} или просто ""
_EMPTY_PATTERNS = ("${", "")


class TestLangfuseDevDefaults:
    """Services must have non-empty dev defaults for LANGFUSE keys (pk-lf-dev/sk-lf-dev)."""

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_public_key_has_dev_default(self, compose: dict, service: str):
        env = _get_service_env(compose, service)
        val = str(env.get("LANGFUSE_PUBLIC_KEY", ""))
        # Проверяем что дефолт содержит pk-lf-dev
        assert "pk-lf-dev" in val, (
            f"compose.yml: {service}.LANGFUSE_PUBLIC_KEY must default to pk-lf-dev, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_secret_key_has_dev_default(self, compose: dict, service: str):
        env = _get_service_env(compose, service)
        val = str(env.get("LANGFUSE_SECRET_KEY", ""))
        assert "sk-lf-dev" in val, (
            f"compose.yml: {service}.LANGFUSE_SECRET_KEY must default to sk-lf-dev, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_host_has_docker_default(self, compose: dict, service: str):
        env = _get_service_env(compose, service)
        val = str(env.get("LANGFUSE_HOST", ""))
        assert "langfuse:3000" in val, (
            f"compose.yml: {service}.LANGFUSE_HOST must default to http://langfuse:3000, "
            f"got: {val!r}"
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
