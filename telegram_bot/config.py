"""Bot configuration."""

from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    redis_url: str = Field(
        default="redis://localhost:6379", validation_alias=AliasChoices("redis_url", "REDIS_URL")
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
    llm_base_url: str = Field(
        default="https://api.cerebras.ai/v1",
        validation_alias=AliasChoices("llm_base_url", "LLM_BASE_URL"),
    )
    llm_model: str = Field(
        default="zai-glm-4.7", validation_alias=AliasChoices("llm_model", "LLM_MODEL")
    )

    # Langfuse observability
    langfuse_public_key: str = Field(
        default="",
        validation_alias=AliasChoices("langfuse_public_key", "LANGFUSE_PUBLIC_KEY"),
    )
    langfuse_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("langfuse_secret_key", "LANGFUSE_SECRET_KEY"),
    )
    langfuse_host: str = Field(
        default="http://localhost:3001",
        validation_alias=AliasChoices("langfuse_host", "LANGFUSE_HOST"),
    )

    # RAG settings
    top_k: int = 5
    min_score: float = 0.3

    ***REMOVED*** AI Configuration
    voyage_api_key: str = Field(
        default="", validation_alias=AliasChoices("voyage_api_key", "VOYAGE_API_KEY")
    )
    voyage_model_docs: str = Field(
        default="voyage-4-large",
        validation_alias=AliasChoices("voyage_model_docs", "VOYAGE_MODEL_DOCS"),
    )
    voyage_model_queries: str = Field(
        default="voyage-4-lite",
        validation_alias=AliasChoices("voyage_model_queries", "VOYAGE_MODEL_QUERIES"),
    )
    voyage_model_rerank: str = Field(
        default="rerank-2.5",
        validation_alias=AliasChoices("voyage_model_rerank", "VOYAGE_RERANK_MODEL"),
    )
    voyage_embedding_dim: int = Field(
        default=1024,
        validation_alias=AliasChoices("voyage_embedding_dim", "VOYAGE_EMBEDDING_DIM"),
    )

    # Legacy (for backward compatibility)
    voyage_embed_model: str = Field(
        default="voyage-3-large",
        validation_alias=AliasChoices("voyage_embed_model", "VOYAGE_EMBED_MODEL"),
    )
    voyage_cache_model: str = Field(
        default="voyage-3-lite",
        validation_alias=AliasChoices("voyage_cache_model", "VOYAGE_CACHE_MODEL"),
    )
    voyage_rerank_model: str = Field(
        default="rerank-2",
        validation_alias=AliasChoices("voyage_rerank_model", "VOYAGE_RERANK_MODEL"),
    )

    # Search Configuration
    search_top_k: int = Field(
        default=20, validation_alias=AliasChoices("search_top_k", "SEARCH_TOP_K")
    )
    rerank_top_k: int = Field(
        default=3, validation_alias=AliasChoices("rerank_top_k", "RERANK_TOP_K")
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

    # Retrieval provider (bge_m3_api | voyage)
    retrieval_dense_provider: str = Field(
        default="bge_m3_api",
        validation_alias=AliasChoices("retrieval_dense_provider", "RETRIEVAL_DENSE_PROVIDER"),
    )

    # Rerank provider (colbert | none | voyage)
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

    ***REMOVED*** Connection
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

    ***REMOVED*** Quantization Configuration
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
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    # Domain configuration (configurable per deployment)
    domain: str = Field(
        default="недвижимость", validation_alias=AliasChoices("domain", "BOT_DOMAIN")
    )
    domain_language: str = Field(
        default="ru", validation_alias=AliasChoices("domain_language", "BOT_LANGUAGE")
    )

    # LiveKit (voice calls)
    livekit_url: str = Field(
        default="", validation_alias=AliasChoices("LIVEKIT_URL", "livekit_url")
    )
    livekit_api_key: str = Field(
        default="", validation_alias=AliasChoices("LIVEKIT_API_KEY", "livekit_api_key")
    )
    livekit_api_secret: str = Field(
        default="", validation_alias=AliasChoices("LIVEKIT_API_SECRET", "livekit_api_secret")
    )
    sip_trunk_id: str = Field(
        default="", validation_alias=AliasChoices("SIP_TRUNK_ID", "sip_trunk_id")
    )

    # Voice transcription
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
    guard_ml_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("guard_ml_enabled", "GUARD_ML_ENABLED"),
    )
    llm_guard_url: str = Field(
        default="http://llm-guard:8100",
        validation_alias=AliasChoices("llm_guard_url", "LLM_GUARD_URL"),
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
    client_direct_pipeline_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "client_direct_pipeline_enabled",
            "CLIENT_DIRECT_PIPELINE_ENABLED",
        ),
    )

    # Session summary + CRM (#305)
    session_summary_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("session_summary_enabled", "SESSION_SUMMARY_ENABLED"),
    )
    session_timeout_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("session_timeout_minutes", "SESSION_TIMEOUT_MINUTES"),
    )
    kommo_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("kommo_enabled", "KOMMO_ENABLED"),
    )
    kommo_subdomain: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_subdomain", "KOMMO_SUBDOMAIN"),
    )
    kommo_access_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("kommo_access_token", "KOMMO_ACCESS_TOKEN"),
    )
    kommo_telegram_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_telegram_field_id", "KOMMO_TELEGRAM_FIELD_ID"),
    )
    kommo_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_client_id", "KOMMO_CLIENT_ID"),
    )
    kommo_client_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("kommo_client_secret", "KOMMO_CLIENT_SECRET"),
    )
    kommo_redirect_uri: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_redirect_uri", "KOMMO_REDIRECT_URI"),
    )
    kommo_auth_code: str = Field(
        default="",
        validation_alias=AliasChoices("kommo_auth_code", "KOMMO_AUTH_CODE"),
    )
    kommo_default_pipeline_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_default_pipeline_id", "KOMMO_DEFAULT_PIPELINE_ID"),
    )
    kommo_responsible_user_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("kommo_responsible_user_id", "KOMMO_RESPONSIBLE_USER_ID"),
    )
    kommo_session_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_session_field_id", "KOMMO_SESSION_FIELD_ID"),
    )
    kommo_lead_score_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_lead_score_field_id", "KOMMO_LEAD_SCORE_FIELD_ID"),
    )
    kommo_lead_band_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_lead_band_field_id", "KOMMO_LEAD_BAND_FIELD_ID"),
    )
    kommo_new_status_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_new_status_id", "KOMMO_NEW_STATUS_ID"),
    )
    kommo_service_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_service_field_id", "KOMMO_SERVICE_FIELD_ID"),
    )
    kommo_source_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices("kommo_source_field_id", "KOMMO_SOURCE_FIELD_ID"),
    )
    kommo_telegram_username_field_id: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "kommo_telegram_username_field_id", "KOMMO_TELEGRAM_USERNAME_FIELD_ID"
        ),
    )

    # Nurturing + funnel analytics (#390)
    nurturing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("nurturing_enabled", "NURTURING_ENABLED"),
    )
    nurturing_interval_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("nurturing_interval_minutes", "NURTURING_INTERVAL_MINUTES"),
    )
    funnel_rollup_cron: str = Field(
        default="15 * * * *",
        validation_alias=AliasChoices("funnel_rollup_cron", "FUNNEL_ROLLUP_CRON"),
    )

    # NurturingDispatch worker (#445)
    nurturing_dispatch_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("nurturing_dispatch_enabled", "NURTURING_DISPATCH_ENABLED"),
    )
    nurturing_dispatch_batch: int = Field(
        default=20,
        validation_alias=AliasChoices("nurturing_dispatch_batch", "NURTURING_DISPATCH_BATCH"),
    )
    nurturing_dispatch_cron: str = Field(
        default="0 10 * * *",
        validation_alias=AliasChoices("nurturing_dispatch_cron", "NURTURING_DISPATCH_CRON"),
    )

    # SessionSummaryWorker (#445)
    session_idle_timeout_min: int = Field(
        default=30,
        validation_alias=AliasChoices("session_idle_timeout_min", "SESSION_IDLE_TIMEOUT_MIN"),
    )
    session_summary_poll_sec: int = Field(
        default=300,
        validation_alias=AliasChoices("session_summary_poll_sec", "SESSION_SUMMARY_POLL_SEC"),
    )
    session_summary_model: str = Field(
        default="claude-haiku-4-5",
        validation_alias=AliasChoices("session_summary_model", "SESSION_SUMMARY_MODEL"),
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
        default="postgresql://postgres:postgres@postgres:5432/realestate",
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
    manager_hot_lead_threshold: int = Field(
        default=60,
        validation_alias=AliasChoices("manager_hot_lead_threshold", "MANAGER_HOT_LEAD_THRESHOLD"),
    )
    manager_hot_lead_dedupe_sec: int = Field(
        default=3600,
        validation_alias=AliasChoices("manager_hot_lead_dedupe_sec", "MANAGER_HOT_LEAD_DEDUPE_SEC"),
    )

    # ── Handoff (Forum Topics) ──────────────────────────────────────
    managers_group_id: int | None = Field(
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
    handoff_wait_timeout_min: int = Field(
        default=15,
        validation_alias=AliasChoices("handoff_wait_timeout_min", "HANDOFF_WAIT_TIMEOUT_MIN"),
    )

    @field_validator("manager_ids", mode="before")
    @classmethod
    def parse_manager_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    def get_collection_name(self) -> str:
        """Get collection name based on quantization mode.

        Returns:
            Collection name with appropriate suffix:
            - 'off': base collection name
            - 'scalar': base_scalar
            - 'binary': base_binary
        """
        base = self.qdrant_collection
        for suffix in ["_binary", "_scalar"]:
            base = base.removesuffix(suffix)

        mode = self.qdrant_quantization_mode.lower()
        if mode == "scalar":
            return f"{base}_scalar"
        if mode == "binary":
            return f"{base}_binary"
        return base
