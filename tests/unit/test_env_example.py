"""Verify .env.example contains all BotConfig CRM/manager fields (#402)."""

import re
from pathlib import Path

import pytest


def _parse_env_example() -> set[str]:
    """Parse .env.example and return set of variable names."""
    env_file = Path(".") / ".env.example"
    keys: set[str] = set()
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = re.match(r"^([A-Z_][A-Z0-9_]*)=", line)
            if match:
                keys.add(match.group(1))
    return keys


def test_local_env_contract_uses_root_dotenv_as_canonical_file() -> None:
    """Local docs/tooling should consistently point to the root .env file."""
    readme = Path("README.md").read_text(encoding="utf-8")
    local_dev = Path("docs/LOCAL-DEVELOPMENT.md").read_text(encoding="utf-8")
    docker_doc = Path("DOCKER.md").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")
    bot_config = Path("telegram_bot/config.py").read_text(encoding="utf-8")

    assert "cp .env.example .env" in readme
    assert "cp .env.example .env" in local_dev
    assert "canonical local env file is `.env`" in docker_doc
    assert ".env.local` is not loaded automatically" in readme
    assert ".env.local` is legacy/manual-only and is not auto-loaded" in local_dev
    assert 'env_file=".env"' in bot_config
    assert "uv run --env-file .env python -m telegram_bot.main" in makefile
    assert "[ -f ./.env ] && . ./.env" in makefile
    assert ".env.local" not in bot_config
    assert ".env.local" not in makefile
    assert ".env -> .env.local symlink" not in makefile


class TestEnvExampleCompleteness:
    """Env example must document all CRM and manager config vars."""

    REQUIRED_CRM_VARS = [
        "KOMMO_ENABLED",
        "KOMMO_SUBDOMAIN",
        "KOMMO_ACCESS_TOKEN",
        "KOMMO_TELEGRAM_FIELD_ID",
        "KOMMO_CLIENT_ID",
        "KOMMO_CLIENT_SECRET",
        "KOMMO_REDIRECT_URI",
        "KOMMO_AUTH_CODE",
        "KOMMO_DEFAULT_PIPELINE_ID",
        "KOMMO_RESPONSIBLE_USER_ID",
        "KOMMO_SESSION_FIELD_ID",
        "KOMMO_LEAD_SCORE_FIELD_ID",
        "KOMMO_LEAD_BAND_FIELD_ID",
    ]

    REQUIRED_MANAGER_VARS = [
        "MANAGER_IDS",
        "MANAGER_HOT_LEAD_THRESHOLD",
        "MANAGER_HOT_LEAD_DEDUPE_SEC",
    ]

    REQUIRED_DB_VARS = [
        "REALESTATE_DATABASE_URL",
        "INGESTION_DATABASE_URL",
    ]

    REQUIRED_RUNTIME_VARS = [
        "BOT_USERNAME",
    ]

    @pytest.mark.parametrize("var", REQUIRED_CRM_VARS)
    def test_crm_var_in_env_example(self, var: str):
        keys = _parse_env_example()
        assert var in keys, f"{var} missing from .env.example"

    @pytest.mark.parametrize("var", REQUIRED_MANAGER_VARS)
    def test_manager_var_in_env_example(self, var: str):
        keys = _parse_env_example()
        assert var in keys, f"{var} missing from .env.example"

    @pytest.mark.parametrize("var", REQUIRED_DB_VARS)
    def test_db_var_in_env_example(self, var: str):
        keys = _parse_env_example()
        assert var in keys, f"{var} missing from .env.example"

    @pytest.mark.parametrize("var", REQUIRED_RUNTIME_VARS)
    def test_runtime_var_in_env_example(self, var: str):
        keys = _parse_env_example()
        assert var in keys, f"{var} missing from .env.example"
