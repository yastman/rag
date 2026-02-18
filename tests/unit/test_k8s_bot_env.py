"""Verify k8s bot deployment has CRM env vars (#402)."""

from pathlib import Path

import pytest
import yaml


def _load_k8s_bot_env() -> list[str]:
    """Load env var names from k8s bot deployment."""
    path = Path("k8s/base/bot/deployment.yaml")
    data = yaml.safe_load(path.read_text())
    containers = data["spec"]["template"]["spec"]["containers"]
    bot_container = next(c for c in containers if c["name"] == "bot")
    return [e["name"] for e in bot_container.get("env", [])]


def _load_k8s_secrets_env() -> set[str]:
    """Load variable names from k8s secrets .env.example."""
    path = Path("k8s/secrets/.env.example")
    keys: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key = line.split("=", 1)[0]
            keys.add(key)
    return keys


class TestK8sBotEnv:
    REQUIRED_VARS = [
        "KOMMO_ENABLED",
        "KOMMO_SUBDOMAIN",
        "MANAGER_IDS",
        "REALESTATE_DATABASE_URL",
    ]

    REQUIRED_SECRETS = [
        "KOMMO_ACCESS_TOKEN",
        "KOMMO_CLIENT_ID",
        "KOMMO_CLIENT_SECRET",
    ]

    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_k8s_deployment_has_var(self, var: str):
        env_names = _load_k8s_bot_env()
        assert var in env_names, f"{var} missing from k8s/base/bot/deployment.yaml"

    @pytest.mark.parametrize("var", REQUIRED_SECRETS)
    def test_k8s_secrets_has_var(self, var: str):
        keys = _load_k8s_secrets_env()
        assert var in keys, f"{var} missing from k8s/secrets/.env.example"
