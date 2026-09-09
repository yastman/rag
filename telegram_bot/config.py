"""Bot configuration."""

from __future__ import annotations

import re as _re
from typing import Annotated
from urllib.parse import quote

from pydantic import (
    AliasChoices,
    BeforeValidator,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from src.config.qdrant_policy import resolve_collection_name
from src.runtime.integrations.redis_mode import (
    DEFAULT_REDIS_MODE,
    RedisMode,
    parse_redis_mode,
    validate_redis_mode,
)


def _empty_str_to_false(v: object) -> object:
    """Convert empty string to False (env vars with no value)."""
    if v == "":
        return False
    return v


EmptyStrBool = Annotated[bool, BeforeValidator(_empty_str_to_false)]


def _empty_str_to_none(v: object) -> object:
    """Convert empty string to None for optional int env vars (#2149)."""
    if v == "":
        return None
    return v


def _inject_local_redis_password(
    redis_url: str,
    *,
    redis_password: SecretStr | None,
    redis_url_explicit: bool,
) -> str:
    """Align the native local Redis URL with compose auth defaults."""
    password = redis_password.get_secret_value().strip() if redis_password is not None else ""
    if redis_url_explicit or not password:
        return redis_url
    if "@" in redis_url or redis_url != "redis://localhost:6379":
        return redis_url
    return redis_url.replace("redis://", f"redis://:{quote(password, safe='')}@", 1)


def _parse_int_id_list(v: object) -> list[int]:
    """Parse a comma-separated string or list into a list of int IDs."""
    if isinstance(v, str):
        return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
    if isinstance(v, list):
        return [int(x) for x in v]
    return []


class BotConfig(BaseSettings):
    """Telegram bot configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Telegram
    telegram_token: str = Field(
        default="", validation_alias=AliasChoices("telegram_token", "TELEGRAM_BOT_TOKEN")
    )

    # Services
    bge_m3_url: str = Field(
        default="http://localhost:8000", validation_alias=AliasChoices("bge_m3_url", "BGE_M3_URL")
    )
    redis_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("redis_password", "REDIS_PASSWORD"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        validation_alias=AliasChoices("redis_url", "REDIS_URL"),
    )
    # Honest Redis operating mode (decision #3354). Disabled by default —
    # no Redis import/client/connection — Compose overrides it explicitly
    # to ``single_instance``; scaled deployments use ``multi_instance``.
    redis_mode: RedisMode = Field(
        default=DEFAULT_REDIS_MODE,
        validation_alias=AliasChoices("redis_mode", "REDIS_MODE"),
    )
    qdrant_url: str = Field(
        default="http://localhost:6333", validation_alias=AliasChoices("qdrant_url", "QDRANT_URL")
    )
    qdrant_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("qdrant_api_key", "QDRANT_API_KEY")
    )
    qdrant_collection: str = Field(
        default="gdrive_documents_bge",
        validation_alias=AliasChoices("qdrant_collection", "QDRANT_COLLECTION"),
    )

    # LLM (OpenAI compatible API)
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("llm_api_key", "LLM_API_KEY", "OPENAI_API_KEY"),
    )
    # Deprecated compatibility field; chat routing uses LiteLLM SDK in-process.
    llm_base_url: str = ""
    llm_model: str = Field(
        default="gpt-4o-mini", validation_alias=AliasChoices("llm_model", "LLM_MODEL")
    )

    # Search Configuration (live knobs; retrieval tuning lives in GraphConfig)
    search_top_k: int = Field(
        default=40, validation_alias=AliasChoices("search_top_k", "SEARCH_TOP_K")
    )

    # Rerank provider (colbert | none)
    rerank_provider: str = Field(
        default="colbert", validation_alias=AliasChoices("rerank_provider", "RERANK_PROVIDER")
    )

    # Qdrant Connection
    qdrant_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("qdrant_timeout", "QDRANT_TIMEOUT"),
    )

    # Qdrant Quantization Configuration (single live selector)
    qdrant_quantization_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("qdrant_quantization_mode", "QDRANT_QUANTIZATION_MODE"),
    )

    # Admin user IDs (comma-separated Telegram user IDs)
    admin_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, validation_alias=AliasChoices("admin_ids", "ADMIN_IDS")
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> list[int]:
        return _parse_int_id_list(v)

    # Domain configuration (configurable per deployment)
    domain: str = Field(
        default="недвижимость", validation_alias=AliasChoices("domain", "BOT_DOMAIN")
    )
    domain_language: str = Field(
        default="ru", validation_alias=AliasChoices("domain_language", "BOT_LANGUAGE")
    )

    # Voice transcription — optional and configuration-driven (#3240). Voice
    # input is exposed only when ``voice_enabled`` is set AND a transcription
    # key (``llm_api_key``) is configured; otherwise dialogs fall back to the
    # proven typed-input path.
    voice_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("voice_enabled", "VOICE_ENABLED"),
    )
    show_transcription: bool = Field(
        default=True,
        validation_alias=AliasChoices("show_transcription", "SHOW_TRANSCRIPTION"),
    )
    voice_language: str = Field(
        default="ru",
        validation_alias=AliasChoices("voice_language", "VOICE_LANGUAGE"),
    )
    stt_model: str = Field(
        default="whisper",
        validation_alias=AliasChoices("stt_model", "STT_MODEL"),
    )
    # Whole voice-operation budget (Telegram download + provider STT call).
    voice_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("voice_timeout", "VOICE_TIMEOUT"),
    )

    # Content filtering (#227)
    content_filter_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("content_filter_enabled", "CONTENT_FILTER_ENABLED"),
    )
    guard_mode: str = Field(
        default="hard",
        validation_alias=AliasChoices("guard_mode", "GUARD_MODE"),
    )

    # Apartment extraction model (#240, #310)
    apartment_extraction_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("apartment_extraction_model", "APARTMENT_EXTRACTION_MODEL"),
    )

    # Real Estate Database (realestate DB in shared Postgres)
    realestate_database_url: str = Field(
        default="",
        validation_alias=AliasChoices("realestate_database_url", "REALESTATE_DATABASE_URL"),
    )

    # Manager IDs (comma-separated Telegram user IDs)
    manager_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("manager_ids", "MANAGER_IDS"),
    )
    # ── Handoff (Forum Topics) ──────────────────────────────────────
    handoff_enabled: EmptyStrBool = Field(
        default=False,
        validation_alias=AliasChoices("handoff_enabled", "HANDOFF_ENABLED"),
    )
    managers_group_id: Annotated[int | None, BeforeValidator(_empty_str_to_none)] = Field(
        default=None,
        validation_alias=AliasChoices("managers_group_id", "MANAGERS_GROUP_ID"),
    )
    handoff_ttl_hours: int = Field(
        default=72,
        validation_alias=AliasChoices("handoff_ttl_hours", "HANDOFF_TTL_HOURS"),
    )
    handoff_summary_min_messages: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "handoff_summary_min_messages", "HANDOFF_SUMMARY_MIN_MESSAGES"
        ),
    )
    business_hours_start: int = Field(
        default=9,
        validation_alias=AliasChoices("business_hours_start", "BUSINESS_HOURS_START"),
    )
    business_hours_end: int = Field(
        default=18,
        validation_alias=AliasChoices("business_hours_end", "BUSINESS_HOURS_END"),
    )
    business_hours_tz: str = Field(
        default="Europe/Sofia",
        validation_alias=AliasChoices("business_hours_tz", "BUSINESS_HOURS_TZ"),
    )

    @field_validator("manager_ids", mode="before")
    @classmethod
    def parse_manager_ids(cls, v: object) -> list[int]:
        return _parse_int_id_list(v)

    @field_validator("redis_mode", mode="before")
    @classmethod
    def parse_redis_mode_value(cls, v: object) -> RedisMode:
        """Single parse point for the REDIS_MODE contract (#3362)."""
        return parse_redis_mode(v)  # type: ignore[arg-type]

    @field_validator("telegram_token", mode="after")
    @classmethod
    def validate_telegram_token_format(cls, v: str) -> str:
        if v and not _re.match(r"^\d+:[A-Za-z\d_-]{35,}$", v):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN format invalid — expected <bot_id>:<35+ chars>; "
                "set a real token in .env"
            )
        return v

    @model_validator(mode="after")
    def validate_handoff_contract(self) -> BotConfig:
        self.redis_url = _inject_local_redis_password(
            self.redis_url,
            redis_password=self.redis_password,
            redis_url_explicit="redis_url" in self.model_fields_set,
        )
        if self.handoff_enabled and self.managers_group_id is None:
            raise ValueError("HANDOFF_ENABLED=true but MANAGERS_GROUP_ID is missing")
        # Mode invariants from decision #3354: multi_instance requires a
        # nonempty Redis URL; disabled mode forbids explicitly enabled
        # Redis-only durable features. Errors surface before polling starts.
        validate_redis_mode(
            self.redis_mode,
            redis_url=self.redis_url,
            redis_only_feature_enabled=self.handoff_enabled,
        )
        if not self.llm_api_key:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "No LLM provider key set (LLM_API_KEY / OPENAI_API_KEY / "
                "CEREBRAS_API_KEY). The bot will fail on the first LLM call."
            )
        return self

    def get_collection_name(self) -> str:
        """Get collection name based on quantization mode.

        Returns:
            Collection name with appropriate suffix:
            - 'off': base collection name
            - 'scalar': base_scalar
            - 'binary': base_binary
        """
        return resolve_collection_name(self.qdrant_collection, self.qdrant_quantization_mode)
