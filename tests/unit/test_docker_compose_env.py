"""Verify docker-compose bot service has CRM env vars (#402)."""

from functools import cache
from pathlib import Path

import pytest
import yaml


@cache
def _load_bot_env(compose_file: str) -> dict[str, str]:
    """Load bot service environment from compose file."""
    path = Path(compose_file)
    data = yaml.safe_load(path.read_text())
    bot = data["services"]["bot"]
    env = bot.get("environment", {})
    if isinstance(env, list):
        return {item.split("=", 1)[0]: item.split("=", 1)[1] if "=" in item else "" for item in env}
    return env


REQUIRED_VARS = [
    "KOMMO_ENABLED",
    "KOMMO_SUBDOMAIN",
    "KOMMO_ACCESS_TOKEN",
    "KOMMO_CLIENT_ID",
    "KOMMO_CLIENT_SECRET",
    "KOMMO_REDIRECT_URI",
    "KOMMO_TELEGRAM_FIELD_ID",
    "KOMMO_DEFAULT_PIPELINE_ID",
    "KOMMO_RESPONSIBLE_USER_ID",
    "KOMMO_SESSION_FIELD_ID",
    "KOMMO_LEAD_SCORE_FIELD_ID",
    "KOMMO_LEAD_BAND_FIELD_ID",
    "KOMMO_NEW_STATUS_ID",
    "KOMMO_SERVICE_FIELD_ID",
    "KOMMO_SOURCE_FIELD_ID",
    "KOMMO_TELEGRAM_USERNAME_FIELD_ID",
    "MANAGER_IDS",
    "MANAGER_HOT_LEAD_THRESHOLD",
    "MANAGER_HOT_LEAD_DEDUPE_SEC",
    "REALESTATE_DATABASE_URL",
]

OPTIONAL_LANGFUSE_BOT_VARS = [
    "LANGFUSE_TRACING_ENVIRONMENT",
    "LANGFUSE_FLUSH_AT",
    "LANGFUSE_FLUSH_INTERVAL",
    "LANGFUSE_PROMPT_LABEL",
]


class TestDevComposeEnv:
    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_dev_compose_has_var(self, var: str):
        env = _load_bot_env("docker-compose.dev.yml")
        assert var in env, f"{var} missing from docker-compose.dev.yml bot environment"

    def test_dev_compose_supports_dedicated_bot_token(self):
        env = _load_bot_env("docker-compose.dev.yml")
        assert "TELEGRAM_BOT_TOKEN_DEV" in env["TELEGRAM_BOT_TOKEN"]

    @pytest.mark.parametrize("var", OPTIONAL_LANGFUSE_BOT_VARS)
    def test_dev_compose_has_langfuse_optional_var(self, var: str):
        env = _load_bot_env("docker-compose.dev.yml")
        assert var in env, f"{var} missing from docker-compose.dev.yml bot environment"


class TestVpsComposeEnv:
    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_vps_compose_has_var(self, var: str):
        env = _load_bot_env("docker-compose.vps.yml")
        assert var in env, f"{var} missing from docker-compose.vps.yml bot environment"

    @pytest.mark.parametrize("var", OPTIONAL_LANGFUSE_BOT_VARS)
    def test_vps_compose_has_langfuse_optional_var(self, var: str):
        env = _load_bot_env("docker-compose.vps.yml")
        assert var in env, f"{var} missing from docker-compose.vps.yml bot environment"


@cache
def _load_service_env(compose_file: str, service_name: str) -> dict[str, str]:
    """Load arbitrary service environment from compose file."""
    path = Path(compose_file)
    data = yaml.safe_load(path.read_text())
    service = data["services"][service_name]
    env = service.get("environment", {})
    if isinstance(env, list):
        return {item.split("=", 1)[0]: item.split("=", 1)[1] if "=" in item else "" for item in env}
    return env


class TestLiteLLMComposeEnv:
    @pytest.mark.parametrize("compose_file", ["docker-compose.dev.yml", "docker-compose.vps.yml"])
    def test_litellm_has_database_url(self, compose_file: str):
        env = _load_service_env(compose_file, "litellm")
        assert "DATABASE_URL" in env, (
            f"DATABASE_URL missing from {compose_file} litellm environment"
        )

    @pytest.mark.parametrize("compose_file", ["docker-compose.dev.yml", "docker-compose.vps.yml"])
    def test_litellm_has_langfuse_otel_host(self, compose_file: str):
        env = _load_service_env(compose_file, "litellm")
        assert "LANGFUSE_OTEL_HOST" in env, (
            f"LANGFUSE_OTEL_HOST missing from {compose_file} litellm environment"
        )
