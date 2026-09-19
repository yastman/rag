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


@pytest.mark.parametrize("mode", ["off", "scalar", "binary"])
def test_rendered_collection_and_quantization_match_services(monkeypatch, mode):
    import json
    import os
    import subprocess

    monkeypatch.setenv("QDRANT_COLLECTION", "audit_isolated_collection")
    monkeypatch.setenv("QDRANT_QUANTIZATION_MODE", mode)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "tests/fixtures/compose.ci.env",
            "-f",
            "compose.yml",
            "-f",
            "compose.dev.yml",
            "--profile",
            "full",
            "config",
            "--format",
            "json",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    services = json.loads(result.stdout)["services"]
    for service in ("bot", "ingestion"):
        env = services[service]["environment"]
        assert env["QDRANT_COLLECTION"] == "audit_isolated_collection"
        assert env["QDRANT_QUANTIZATION_MODE"] == mode
