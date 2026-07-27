from __future__ import annotations

from enum import StrEnum

from pydantic import AnyHttpUrl, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Command(StrEnum):
    INGEST = "ingest"
    BOT = "bot"
    SMOKE = "smoke"


class SettingsConfigurationError(ValueError):
    def __init__(self, command: Command, missing: list[str], invalid: list[str]) -> None:
        self.missing = tuple(missing)
        self.invalid = tuple(invalid)
        details = [*missing, *invalid]
        super().__init__(f"{command.value} configuration requires: {', '.join(details)}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        extra="ignore",
        validate_default=True,
    )

    collection: str | None = None
    qdrant_url: AnyHttpUrl = "http://127.0.0.1:6333"
    redis_url: RedisDsn = "redis://127.0.0.1:6379/0"
    bge_url: AnyHttpUrl = "http://127.0.0.1:8080"
    litellm_model: str = "openai/gpt-4.1-mini"
    litellm_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_allowed_user_ids: str | None = None

    def validate_for(self, command: Command, *, collection: str | None = None) -> None:
        missing: list[str] = []
        invalid: list[str] = []
        resolved_collection = collection if collection is not None else self.collection

        if not _present(resolved_collection):
            if command is Command.SMOKE:
                missing.append("--collection")
            elif command in {Command.INGEST, Command.BOT}:
                missing.append("RAG_COLLECTION")
        if command in {Command.BOT, Command.SMOKE} and not _present(self.litellm_api_key):
            missing.append("RAG_LITELLM_API_KEY")
        if command is Command.BOT:
            if not _present(self.telegram_bot_token):
                missing.append("RAG_TELEGRAM_BOT_TOKEN")
            if not _present(self.telegram_allowed_user_ids):
                missing.append("RAG_TELEGRAM_ALLOWED_USER_IDS")
            elif not _valid_allowed_users(self.telegram_allowed_user_ids):
                invalid.append("RAG_TELEGRAM_ALLOWED_USER_IDS")

        if missing or invalid:
            raise SettingsConfigurationError(command, missing, invalid)


def _present(value: str | SecretStr | None) -> bool:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return bool(value and value.strip())


def _valid_allowed_users(value: str) -> bool:
    value = value.strip()
    if value == "*":
        return True
    users = [user.strip() for user in value.split(",")]
    return bool(users) and all(user.isascii() and user.isdecimal() for user in users)
