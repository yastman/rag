"""Verify docker-compose bot service has CRM env vars (#402)."""

from pathlib import Path

import pytest
import yaml


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
    "KOMMO_SESSION_FIELD_ID",
    "KOMMO_LEAD_SCORE_FIELD_ID",
    "KOMMO_LEAD_BAND_FIELD_ID",
    "MANAGER_IDS",
    "MANAGER_HOT_LEAD_THRESHOLD",
    "MANAGER_HOT_LEAD_DEDUPE_SEC",
    "REALESTATE_DATABASE_URL",
]


class TestDevComposeEnv:
    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_dev_compose_has_var(self, var: str):
        env = _load_bot_env("docker-compose.dev.yml")
        assert var in env, f"{var} missing from docker-compose.dev.yml bot environment"


class TestVpsComposeEnv:
    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_vps_compose_has_var(self, var: str):
        env = _load_bot_env("docker-compose.vps.yml")
        assert var in env, f"{var} missing from docker-compose.vps.yml bot environment"
