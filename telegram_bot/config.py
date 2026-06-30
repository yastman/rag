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
    qdrant_history_collection: str = Field(
        default="conversation_history",
        validation_alias=AliasChoices("qdrant_history_collection", "QDRANT_HISTORY_COLLECTION"),
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

    # RAG settings
    top_k: int = 5
    min_score: float = 0.3

    # Search Configuration
    search_top_k: int = Field(
        default=40, validation_alias=AliasChoices("search_top_k", "SEARCH_TOP_K")
    )
    rerank_top_k: int = Field(
        default=7, validation_alias=AliasChoices("rerank_top_k", "RERANK_TOP_K")
    )
    rerank_candidates_max: int = Field(
        default=10,
        validation_alias=AliasChoices("rerank_candidates_max", "RERANK_CANDIDATES_MAX"),
    )

    # CESC Configuration
    cesc_enabled: bool = Field(
        default=True, validation_alias=AliasChoices("cesc_enabled", "CESC_ENABLED")
    )
    cesc_extraction_frequency: int = Field(
        default=3,
        validation_alias=AliasChoices("cesc_extraction_frequency", "CESC_EXTRACTION_FREQUENCY"),
    )
    user_context_ttl: int = Field(
        default=30 * 24 * 3600,
        validation_alias=AliasChoices("user_context_ttl", "USER_CONTEXT_TTL"),
    )

    # Rerank provider (colbert | none)
    rerank_provider: str = Field(
        default="colbert", validation_alias=AliasChoices("rerank_provider", "RERANK_PROVIDER")
    )

    # Hybrid Search Configuration
    hybrid_dense_weight: float = Field(
        default=0.6,
        validation_alias=AliasChoices("hybrid_dense_weight", "HYBRID_DENSE_WEIGHT"),
    )
    hybrid_sparse_weight: float = Field(
        default=0.4,
        validation_alias=AliasChoices("hybrid_sparse_weight", "HYBRID_SPARSE_WEIGHT"),
    )

    # Qdrant Connection
    qdrant_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("qdrant_timeout", "QDRANT_TIMEOUT"),
    )

    # Score Boosting Configuration
    freshness_boost_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("freshness_boost_enabled", "FRESHNESS_BOOST"),
    )
    freshness_field: str = Field(
        default="created_at",
        validation_alias=AliasChoices("freshness_field", "FRESHNESS_FIELD"),
    )
    freshness_scale_days: int = Field(
        default=30,
        validation_alias=AliasChoices("freshness_scale_days", "FRESHNESS_SCALE_DAYS"),
    )

    # MMR Diversity Configuration
    mmr_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("mmr_enabled", "MMR_ENABLED")
    )
    mmr_lambda: float = Field(
        default=0.7, validation_alias=AliasChoices("mmr_lambda", "MMR_LAMBDA")
    )

    # Qdrant Quantization Configuration
    qdrant_quantization_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("qdrant_quantization_mode", "QDRANT_QUANTIZATION_MODE"),
    )
    qdrant_use_quantization: bool = Field(
        default=True,
        validation_alias=AliasChoices("qdrant_use_quantization", "QDRANT_USE_QUANTIZATION"),
    )
    qdrant_quantization_rescore: bool = Field(
        default=True,
        validation_alias=AliasChoices("qdrant_quantization_rescore", "QDRANT_QUANTIZATION_RESCORE"),
    )
    qdrant_quantization_oversampling: float = Field(
        default=2.0,
        validation_alias=AliasChoices(
            "qdrant_quantization_oversampling", "QDRANT_QUANTIZATION_OVERSAMPLING"
        ),
    )
    qdrant_quantization_always_ram: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "qdrant_quantization_always_ram", "QDRANT_QUANTIZATION_ALWAYS_RAM"
        ),
    )

    # HyDE (Hypothetical Document Embeddings)
    use_hyde: bool = Field(default=False, validation_alias=AliasChoices("use_hyde", "USE_HYDE"))
    hyde_min_words: int = Field(
        default=5, validation_alias=AliasChoices("hyde_min_words", "HYDE_MIN_WORDS")
    )

    # Semantic cache tuning
    semantic_cache_threshold: float = Field(
        default=0.10,
        validation_alias=AliasChoices("semantic_cache_threshold", "SEMANTIC_CACHE_THRESHOLD"),
    )
    semantic_cache_ttl_default: int = Field(
        default=3600,
        validation_alias=AliasChoices("semantic_cache_ttl_default", "SEMANTIC_CACHE_TTL_DEFAULT"),
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

    # Voice transcription (optional-profile: voice; kept because bot.py reads these)
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

    # Content filtering (#227)
    content_filter_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("content_filter_enabled", "CONTENT_FILTER_ENABLED"),
    )
    guard_mode: str = Field(
        default="hard",
        validation_alias=AliasChoices("guard_mode", "GUARD_MODE"),
    )
    # Guardrails
    enable_confidence_scoring: bool = Field(
        default=False,
        validation_alias=AliasChoices("enable_confidence_scoring", "ENABLE_CONFIDENCE_SCORING"),
    )
    enable_off_topic_detection: bool = Field(
        default=True,
        validation_alias=AliasChoices("enable_off_topic_detection", "ENABLE_OFF_TOPIC_DETECTION"),
    )
    low_confidence_threshold: float = Field(
        default=0.3,
        validation_alias=AliasChoices("low_confidence_threshold", "LOW_CONFIDENCE_THRESHOLD"),
    )

    # Small-to-big context expansion
    small_to_big_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("small_to_big_mode", "SMALL_TO_BIG_MODE"),
    )
    small_to_big_window_before: int = Field(
        default=1,
        validation_alias=AliasChoices("small_to_big_window_before", "SMALL_TO_BIG_WINDOW_BEFORE"),
    )
    small_to_big_window_after: int = Field(
        default=1,
        validation_alias=AliasChoices("small_to_big_window_after", "SMALL_TO_BIG_WINDOW_AFTER"),
    )
    max_expanded_chunks: int = Field(
        default=10,
        validation_alias=AliasChoices("max_expanded_chunks", "MAX_EXPANDED_CHUNKS"),
    )
    max_context_tokens: int = Field(
        default=8000,
        validation_alias=AliasChoices("max_context_tokens", "MAX_CONTEXT_TOKENS"),
    )

    # Supervisor routing model (#240, #310 — supervisor-only since v3.3)
    supervisor_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("supervisor_model", "SUPERVISOR_MODEL"),
    )
    apartment_extraction_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("apartment_extraction_model", "APARTMENT_EXTRACTION_MODEL"),
    )
    client_direct_pipeline_enabled: EmptyStrBool = Field(
        default=False,
        validation_alias=AliasChoices(
            "client_direct_pipeline_enabled",
            "CLIENT_DIRECT_PIPELINE_ENABLED",
        ),
    )
    supervisor_max_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices(
            "supervisor_max_tokens",
            "SUPERVISOR_MAX_TOKENS",
        ),
    )

    # Call limits (#374)
    max_llm_calls: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("max_llm_calls", "MAX_LLM_CALLS"),
    )
    max_tool_calls: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("max_tool_calls", "MAX_TOOL_CALLS"),
    )

    # LLM-as-a-Judge online sampling
    judge_sample_rate: float = Field(
        default=0.0,
        validation_alias=AliasChoices("JUDGE_SAMPLE_RATE", "judge_sample_rate"),
        description="Fraction of queries to evaluate with LLM-as-a-Judge (0.0 = off, 0.2 = 20%)",
    )
    judge_model: str = Field(
        default="gpt-4o-mini-cerebras-glm",
        validation_alias=AliasChoices("JUDGE_MODEL", "judge_model"),
        description="LLM model for judge evaluation",
    )

    # Agent checkpointer TTL (#424)
    agent_checkpointer_ttl_minutes: int = Field(
        default=120,
        validation_alias=AliasChoices(
            "agent_checkpointer_ttl_minutes", "AGENT_CHECKPOINTER_TTL_MINUTES"
        ),
    )

    # Sliding window for agent history (#519)
    agent_max_history_messages: int = Field(
        default=15,
        ge=1,
        validation_alias=AliasChoices("agent_max_history_messages", "AGENT_MAX_HISTORY_MESSAGES"),
    )

    # Real Estate Database (realestate DB in shared Postgres)
    realestate_database_url: str = Field(
        default="",
        validation_alias=AliasChoices("realestate_database_url", "REALESTATE_DATABASE_URL"),
    )

    # History search (#433)
    history_relevance_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("history_relevance_threshold", "HISTORY_RELEVANCE_THRESHOLD"),
    )

    # i18n
    supported_locales: list[str] = Field(
        default=["ru", "en", "uk"],
        validation_alias=AliasChoices("supported_locales", "SUPPORTED_LOCALES"),
    )
    default_locale: str = Field(
        default="ru",
        validation_alias=AliasChoices("default_locale", "DEFAULT_LOCALE"),
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
