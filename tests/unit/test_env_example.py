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
