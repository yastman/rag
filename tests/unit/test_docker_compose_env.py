"""Verify docker-compose bot service has required env vars (#402, updated #2635)."""

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


# Kommo CRM vars removed — CRM surface archived in #2625.
REQUIRED_VARS = [
    "MANAGER_IDS",
    "REALESTATE_DATABASE_URL",
]


class TestDevComposeEnv:
    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_dev_compose_has_var(self, var: str):
        env = _load_bot_env("compose.yml")
        assert var in env, f"{var} missing from compose.yml bot environment"


class TestVpsComposeEnv:
    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_vps_compose_has_var(self, var: str):
        env = _load_bot_env("compose.yml")
        assert var in env, f"{var} missing from compose.yml bot environment"
