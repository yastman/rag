"""Regression tests for the k3s secret template and generation flow."""

from pathlib import Path


API_KEYS_REQUIRED = {
    "TELEGRAM_BOT_TOKEN",
    "LITELLM_MASTER_KEY",
    "REDIS_PASSWORD",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "KOMMO_ACCESS_TOKEN",
    "KOMMO_CLIENT_ID",
    "KOMMO_CLIENT_SECRET",
}


def _load_env_example_keys() -> set[str]:
    path = Path("k8s/secrets/.env.example")
    keys: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key = line.split("=", 1)[0]
            keys.add(key)
    return keys


def test_env_example_documents_current_api_keys_contract() -> None:
    keys = _load_env_example_keys()
    assert keys >= API_KEYS_REQUIRED


def test_env_example_documents_postgres_password_for_db_credentials() -> None:
    keys = _load_env_example_keys()
    assert "POSTGRES_PASSWORD" in keys


def test_make_k3s_secrets_uses_env_postgres_password() -> None:
    makefile = Path("Makefile").read_text()
    assert "set -a; . k8s/secrets/.env; set +a;" in makefile
    assert "--from-literal=POSTGRES_PASSWORD=$$POSTGRES_PASSWORD" in makefile
    assert "--from-literal=POSTGRES_PASSWORD=postgres" not in makefile
