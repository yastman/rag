"""GraphConfig — configuration for the imperative RAG runtime.

Moved from ``telegram_bot/graph/config.py`` as the second slice of the
reverse-layering fix tracked under #1948 / #2045 / #2049. The legacy
``telegram_bot.graph.config`` module is kept as a thin re-export so
existing imports across the test suite, ``telegram_bot/`` internals, and
external consumers continue to work without churn.

Provides service factories for LLM, embeddings, and cache thresholds.

#2482: GraphConfig is now a composition of focused config classes.
#2577: Flat @property accessors are generated automatically from _FLAT_KWARGS,
removing the duplicated manual getter/setter pairs. The constructor still
accepts legacy flat kwargs so existing call-sites like
``GraphConfig(llm_model="x", bge_m3_url="y")`` continue to work.
#card_176c964330b6: sub-configs migrated to BaseModel; env-loading via
pydantic-settings BaseSettings (_GraphEnvSettings), dropping manual os.getenv
casting in from_env().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-config models (pydantic BaseModel — validated, no env-loading)
# ---------------------------------------------------------------------------


class LlmConfig(BaseModel):
    """LLM provider and generation settings."""

    # Deprecated compatibility field; LiteLLM SDK routing no longer uses a proxy base URL.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    generate_max_tokens: int = 1024
    # Reasoning control for Cerebras models (#reasoning)
    reasoning_effort: str | None = None  # "low"/"medium"/"high" (gpt-oss-120b)
    reasoning_format: str | None = None  # "hidden"/"parsed"/"raw"/"none"
    disable_reasoning: bool | None = None  # True/False (zai-glm-4.7)
    rewrite_model: str = "gpt-4o-mini"
    rewrite_max_tokens: int = 64

    model_config = {"arbitrary_types_allowed": True}

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        """Return SDK-shaped reasoning params for chat.completions.create()."""
        extra_body: dict[str, Any] = {}
        if self.disable_reasoning is not None:
            extra_body["disable_reasoning"] = self.disable_reasoning
            return {"extra_body": extra_body}

        kwargs: dict[str, Any] = {}
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.reasoning_format is not None:
            extra_body["reasoning_format"] = self.reasoning_format
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs


class RetrievalConfig(BaseModel):
    """Qdrant, BGE-M3, search, and rerank settings."""

    bge_m3_url: str = "http://bge-m3:8000"
    bge_m3_timeout: float = 120.0
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "gdrive_documents_bge"
    search_top_k: int = 40
    rerank_top_k: int = 7
    redis_url: str = "redis://redis:6379"
    max_rewrite_attempts: int = 1
    # RRF score scale: 1/(rank+k), k=60 default. Top-1 = ~0.016, Top-20 last = ~0.012.
    # skip_rerank_threshold >= 0.018 means top-1 result already has very high rank — safe to skip
    # ColBERT rerank. Must be > 1/61≈0.016 to ensure ColBERT runs on borderline cases.
    skip_rerank_threshold: float = 0.018
    # RRF score scale: threshold 0.005 accepts all top-20 results (~0.012..0.016 typical range).
    # This is intentional — loose filter that only rejects truly irrelevant results (score < 0.005).
    relevance_threshold_rrf: float = 0.005
    score_improvement_delta: float = 0.001
    rerank_provider: str = "colbert"
    # Small-to-big context expansion
    small_to_big_mode: str = "on"
    small_to_big_window_before: int = 0
    small_to_big_window_after: int = 2
    max_expanded_chunks: int = 10
    max_context_tokens: int = 8000


class CacheConfig(BaseModel):
    """Redis cache thresholds and TTLs."""

    cache_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "FAQ": 0.12,
            "ENTITY": 0.10,
            "GENERAL": 0.08,
            "STRUCTURED": 0.05,
        }
    )
    cache_ttl: dict[str, int] = Field(
        default_factory=lambda: {
            "FAQ": 86400,  # 24h
            "ENTITY": 3600,  # 1h
            "GENERAL": 3600,  # 1h
            "STRUCTURED": 7200,  # 2h
        }
    )


class DomainConfig(BaseModel):
    """Domain identity and language settings."""

    domain: str = "недвижимость"
    domain_language: str = "ru"


class ResponseConfig(BaseModel):
    """Response style, sources, streaming, and classifier settings."""

    # Response length control rollout (#129)
    response_style_enabled: bool = False
    response_style_shadow_mode: bool = False
    # Source attribution (#225)
    show_sources: bool = False
    streaming_enabled: bool = True
    # TTFT drift warning threshold in ms (#675); raise for reasoning models behind proxy
    ttft_drift_warn_ms: int = 500
    # Query classifier mode (#805): "regex" (default) or "semantic" (RedisVL SemanticRouter)
    classifier_mode: str = "regex"


class VoiceConfig(BaseModel):
    """Voice transcription settings."""

    # Voice transcription (#151)
    show_transcription: bool = True
    voice_language: str = "ru"
    stt_model: str = "whisper"


class SecurityConfig(BaseModel):
    """Guard and content filter settings."""

    # Prompt injection defense (#226)
    guard_mode: str = "hard"  # "hard" = block, "soft" = flag + continue, "log" = log only
    # Content filtering (#227)
    content_filter_enabled: bool = True


# ---------------------------------------------------------------------------
# Env-loading settings (pydantic-settings) — used only by from_env()
# ---------------------------------------------------------------------------


class _GraphEnvSettings(BaseSettings):
    """Flat env-var loader for GraphConfig.from_env().

    Reads all environment variables that GraphConfig cares about,
    with proper type coercion handled by pydantic-settings.
    Not part of the public API — use GraphConfig.from_env().
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("llm_api_key", "LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("llm_model", "LLM_MODEL"),
    )
    llm_temperature: float = Field(
        default=0.7,
        validation_alias=AliasChoices("llm_temperature", "LLM_TEMPERATURE"),
    )
    llm_max_tokens: int = Field(
        default=4096,
        validation_alias=AliasChoices("llm_max_tokens", "LLM_MAX_TOKENS"),
    )
    generate_max_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices("generate_max_tokens", "GENERATE_MAX_TOKENS"),
    )
    reasoning_effort: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reasoning_effort", "REASONING_EFFORT"),
    )
    reasoning_format: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reasoning_format", "REASONING_FORMAT"),
    )
    disable_reasoning: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("disable_reasoning", "DISABLE_REASONING"),
    )
    rewrite_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("rewrite_model", "REWRITE_MODEL"),
    )
    rewrite_max_tokens: int = Field(
        default=64,
        validation_alias=AliasChoices("rewrite_max_tokens", "REWRITE_MAX_TOKENS"),
    )

    # Retrieval
    bge_m3_url: str = Field(
        default="http://bge-m3:8000",
        validation_alias=AliasChoices("bge_m3_url", "BGE_M3_URL"),
    )
    bge_m3_timeout: float = Field(
        default=120.0,
        validation_alias=AliasChoices("bge_m3_timeout", "BGE_M3_TIMEOUT"),
    )
    qdrant_url: str = Field(
        default="http://qdrant:6333",
        validation_alias=AliasChoices("qdrant_url", "QDRANT_URL"),
    )
    qdrant_collection: str = Field(
        default="gdrive_documents_bge",
        validation_alias=AliasChoices("qdrant_collection", "QDRANT_COLLECTION"),
    )
    search_top_k: int = Field(
        default=40,
        validation_alias=AliasChoices("search_top_k", "SEARCH_TOP_K"),
    )
    rerank_top_k: int = Field(
        default=7,
        validation_alias=AliasChoices("rerank_top_k", "RERANK_TOP_K"),
    )
    redis_url: str = Field(
        default="redis://redis:6379",
        validation_alias=AliasChoices("redis_url", "REDIS_URL"),
    )
    max_rewrite_attempts: int = Field(
        default=1,
        validation_alias=AliasChoices("max_rewrite_attempts", "MAX_REWRITE_ATTEMPTS"),
    )
    skip_rerank_threshold: float = Field(
        default=0.018,
        validation_alias=AliasChoices("skip_rerank_threshold", "SKIP_RERANK_THRESHOLD"),
    )
    relevance_threshold_rrf: float = Field(
        default=0.005,
        validation_alias=AliasChoices("relevance_threshold_rrf", "RELEVANCE_THRESHOLD_RRF"),
    )
    score_improvement_delta: float = Field(
        default=0.001,
        validation_alias=AliasChoices("score_improvement_delta", "SCORE_IMPROVEMENT_DELTA"),
    )
    rerank_provider: str = Field(
        default="colbert",
        validation_alias=AliasChoices("rerank_provider", "RERANK_PROVIDER"),
    )
    small_to_big_mode: str = Field(
        default="on",
        validation_alias=AliasChoices("small_to_big_mode", "SMALL_TO_BIG_MODE"),
    )
    small_to_big_window_before: int = Field(
        default=0,
        validation_alias=AliasChoices("small_to_big_window_before", "SMALL_TO_BIG_WINDOW_BEFORE"),
    )
    small_to_big_window_after: int = Field(
        default=2,
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

    # Domain
    domain: str = Field(
        default="недвижимость",
        validation_alias=AliasChoices("domain", "BOT_DOMAIN"),
    )
    domain_language: str = Field(
        default="ru",
        validation_alias=AliasChoices("domain_language", "BOT_LANGUAGE"),
    )

    # Response
    response_style_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("response_style_enabled", "RESPONSE_STYLE_ENABLED"),
    )
    response_style_shadow_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("response_style_shadow_mode", "RESPONSE_STYLE_SHADOW_MODE"),
    )
    show_sources: bool = Field(
        default=False,
        validation_alias=AliasChoices("show_sources", "SHOW_SOURCES"),
    )
    streaming_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("streaming_enabled", "STREAMING_ENABLED"),
    )
    ttft_drift_warn_ms: int = Field(
        default=500,
        validation_alias=AliasChoices("ttft_drift_warn_ms", "TTFT_DRIFT_WARN_MS"),
    )
    classifier_mode: str = Field(
        default="regex",
        validation_alias=AliasChoices("classifier_mode", "CLASSIFIER_MODE"),
    )

    # Voice
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

    # Security
    guard_mode: str = Field(
        default="hard",
        validation_alias=AliasChoices("guard_mode", "GUARD_MODE"),
    )
    content_filter_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("content_filter_enabled", "CONTENT_FILTER_ENABLED"),
    )


# ---------------------------------------------------------------------------
# Mapping from legacy flat kwarg name -> (sub_config_attr, sub_config_field).
# This is the single source of truth for backward-compatible flat access (#2577).
# ---------------------------------------------------------------------------

_FLAT_KWARGS: dict[str, tuple[str, str]] = {
    # LLM
    "llm_base_url": ("llm", "llm_base_url"),
    "llm_api_key": ("llm", "llm_api_key"),
    "llm_model": ("llm", "llm_model"),
    "llm_temperature": ("llm", "llm_temperature"),
    "llm_max_tokens": ("llm", "llm_max_tokens"),
    "generate_max_tokens": ("llm", "generate_max_tokens"),
    "reasoning_effort": ("llm", "reasoning_effort"),
    "reasoning_format": ("llm", "reasoning_format"),
    "disable_reasoning": ("llm", "disable_reasoning"),
    "rewrite_model": ("llm", "rewrite_model"),
    "rewrite_max_tokens": ("llm", "rewrite_max_tokens"),
    # Retrieval
    "bge_m3_url": ("retrieval", "bge_m3_url"),
    "bge_m3_timeout": ("retrieval", "bge_m3_timeout"),
    "qdrant_url": ("retrieval", "qdrant_url"),
    "qdrant_collection": ("retrieval", "qdrant_collection"),
    "search_top_k": ("retrieval", "search_top_k"),
    "rerank_top_k": ("retrieval", "rerank_top_k"),
    "redis_url": ("retrieval", "redis_url"),
    "max_rewrite_attempts": ("retrieval", "max_rewrite_attempts"),
    "skip_rerank_threshold": ("retrieval", "skip_rerank_threshold"),
    "relevance_threshold_rrf": ("retrieval", "relevance_threshold_rrf"),
    "score_improvement_delta": ("retrieval", "score_improvement_delta"),
    "rerank_provider": ("retrieval", "rerank_provider"),
    "small_to_big_mode": ("retrieval", "small_to_big_mode"),
    "small_to_big_window_before": ("retrieval", "small_to_big_window_before"),
    "small_to_big_window_after": ("retrieval", "small_to_big_window_after"),
    "max_expanded_chunks": ("retrieval", "max_expanded_chunks"),
    "max_context_tokens": ("retrieval", "max_context_tokens"),
    # Cache
    "cache_thresholds": ("cache", "cache_thresholds"),
    "cache_ttl": ("cache", "cache_ttl"),
    # Domain
    "domain": ("domain_cfg", "domain"),
    "domain_language": ("domain_cfg", "domain_language"),
    # Response
    "response_style_enabled": ("response", "response_style_enabled"),
    "response_style_shadow_mode": ("response", "response_style_shadow_mode"),
    "show_sources": ("response", "show_sources"),
    "streaming_enabled": ("response", "streaming_enabled"),
    "ttft_drift_warn_ms": ("response", "ttft_drift_warn_ms"),
    "classifier_mode": ("response", "classifier_mode"),
    # Voice
    "show_transcription": ("voice", "show_transcription"),
    "voice_language": ("voice", "voice_language"),
    "stt_model": ("voice", "stt_model"),
    # Security
    "guard_mode": ("security", "guard_mode"),
    "content_filter_enabled": ("security", "content_filter_enabled"),
}


def _make_flat_property(sub_attr: str, sub_field: str) -> property:
    """Build a getter+setter property that routes through a sub-config attribute."""

    def _get(self: Any) -> Any:
        return getattr(getattr(self, sub_attr), sub_field)

    def _set(self: Any, v: Any) -> None:
        setattr(getattr(self, sub_attr), sub_field, v)

    return property(_get, _set)


@dataclass(init=False)
class GraphConfig:
    """Configuration for the imperative RAG runtime.

    Composed from focused sub-config classes (#2482). Flat attribute
    access (e.g. ``config.llm_model``, ``config.domain``) is preserved
    via auto-generated properties from ``_FLAT_KWARGS`` (#2577) for
    backward compatibility with all existing callers.
    The constructor also accepts legacy flat kwargs (e.g.
    ``GraphConfig(llm_model="x")``) so existing call-sites continue to work.

    Sub-configs are accessible directly::

        cfg.llm.llm_model
        cfg.retrieval.search_top_k
        cfg.domain_cfg.domain
    """

    llm: LlmConfig
    retrieval: RetrievalConfig
    cache: CacheConfig
    # Named ``domain_cfg`` to avoid clash with the ``domain`` string property below.
    domain_cfg: DomainConfig
    response: ResponseConfig
    voice: VoiceConfig
    security: SecurityConfig

    if TYPE_CHECKING:
        # mypy stubs for flat compat accessors generated at runtime from _FLAT_KWARGS.
        # At runtime these properties are injected via setattr() after class creation.
        # LLM
        llm_base_url: str
        llm_api_key: str
        llm_model: str
        llm_temperature: float
        llm_max_tokens: int
        generate_max_tokens: int
        reasoning_effort: str | None
        reasoning_format: str | None
        disable_reasoning: bool | None
        rewrite_model: str
        rewrite_max_tokens: int
        # Retrieval
        bge_m3_url: str
        bge_m3_timeout: float
        qdrant_url: str
        qdrant_collection: str
        search_top_k: int
        rerank_top_k: int
        redis_url: str
        max_rewrite_attempts: int
        skip_rerank_threshold: float
        relevance_threshold_rrf: float
        score_improvement_delta: float
        rerank_provider: str
        small_to_big_mode: str
        small_to_big_window_before: int
        small_to_big_window_after: int
        max_expanded_chunks: int
        max_context_tokens: int
        # Cache
        cache_thresholds: dict[str, float]
        cache_ttl: dict[str, int]
        # Domain
        domain: str
        domain_language: str
        # Response
        response_style_enabled: bool
        response_style_shadow_mode: bool
        show_sources: bool
        streaming_enabled: bool
        ttft_drift_warn_ms: int
        classifier_mode: str
        # Voice
        show_transcription: bool
        voice_language: str
        stt_model: str
        # Security
        guard_mode: str
        content_filter_enabled: bool

    def __init__(
        self,
        llm: LlmConfig | None = None,
        retrieval: RetrievalConfig | None = None,
        cache: CacheConfig | None = None,
        domain_cfg: DomainConfig | None = None,
        response: ResponseConfig | None = None,
        voice: VoiceConfig | None = None,
        security: SecurityConfig | None = None,
        **flat_kwargs: Any,
    ) -> None:
        """Accept both sub-config objects and legacy flat kwargs.

        Flat kwargs (e.g. ``llm_model="x"``) are applied *after* the
        sub-config defaults, so they override only the specified fields.
        """
        self.llm = llm if llm is not None else LlmConfig()
        self.retrieval = retrieval if retrieval is not None else RetrievalConfig()
        self.cache = cache if cache is not None else CacheConfig()
        self.domain_cfg = domain_cfg if domain_cfg is not None else DomainConfig()
        self.response = response if response is not None else ResponseConfig()
        self.voice = voice if voice is not None else VoiceConfig()
        self.security = security if security is not None else SecurityConfig()

        for key, value in flat_kwargs.items():
            if key not in _FLAT_KWARGS:
                raise TypeError(f"GraphConfig() got unexpected keyword argument {key!r}")
            sub_attr, sub_field = _FLAT_KWARGS[key]
            setattr(getattr(self, sub_attr), sub_field, value)

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        """Return SDK-shaped reasoning params for chat.completions.create().

        ``reasoning_effort`` is part of the OpenAI Python SDK chat completions
        schema. Provider-specific LiteLLM/Cerebras/Z.ai controls must travel in
        ``extra_body`` so the OpenAI-compatible client does not reject them as
        unexpected top-level kwargs.
        """
        return self.llm.get_reasoning_kwargs()

    @classmethod
    def from_env(cls) -> GraphConfig:
        """Create GraphConfig from environment variables.

        Delegates env-var parsing and type coercion to pydantic-settings
        (_GraphEnvSettings), then assembles sub-configs from the loaded values.
        """
        e = _GraphEnvSettings()
        return cls(
            llm=LlmConfig(
                llm_api_key=e.llm_api_key,
                llm_model=e.llm_model,
                llm_temperature=e.llm_temperature,
                llm_max_tokens=e.llm_max_tokens,
                generate_max_tokens=e.generate_max_tokens,
                reasoning_effort=e.reasoning_effort or None,
                reasoning_format=e.reasoning_format or None,
                disable_reasoning=e.disable_reasoning,
                rewrite_model=e.rewrite_model or e.llm_model,
                rewrite_max_tokens=e.rewrite_max_tokens,
            ),
            retrieval=RetrievalConfig(
                bge_m3_url=e.bge_m3_url,
                bge_m3_timeout=e.bge_m3_timeout,
                qdrant_url=e.qdrant_url,
                qdrant_collection=e.qdrant_collection,
                search_top_k=e.search_top_k,
                rerank_top_k=e.rerank_top_k,
                redis_url=e.redis_url,
                max_rewrite_attempts=e.max_rewrite_attempts,
                skip_rerank_threshold=e.skip_rerank_threshold,
                relevance_threshold_rrf=e.relevance_threshold_rrf,
                score_improvement_delta=e.score_improvement_delta,
                rerank_provider=e.rerank_provider,
                small_to_big_mode=e.small_to_big_mode,
                small_to_big_window_before=e.small_to_big_window_before,
                small_to_big_window_after=e.small_to_big_window_after,
                max_expanded_chunks=e.max_expanded_chunks,
                max_context_tokens=e.max_context_tokens,
            ),
            domain_cfg=DomainConfig(
                domain=e.domain,
                domain_language=e.domain_language,
            ),
            response=ResponseConfig(
                response_style_enabled=e.response_style_enabled,
                response_style_shadow_mode=e.response_style_shadow_mode,
                show_sources=e.show_sources,
                streaming_enabled=e.streaming_enabled,
                ttft_drift_warn_ms=e.ttft_drift_warn_ms,
                classifier_mode=e.classifier_mode,
            ),
            voice=VoiceConfig(
                show_transcription=e.show_transcription,
                voice_language=e.voice_language,
                stt_model=e.stt_model,
            ),
            security=SecurityConfig(
                guard_mode=e.guard_mode,
                content_filter_enabled=e.content_filter_enabled,
            ),
        )

    def create_llm(self, model_override: str | None = None, *, auto_trace: bool = True) -> Any:
        """Create an OpenAI-shaped chat client backed by LiteLLM SDK routing."""
        _ = auto_trace
        from src.runtime.llm import create_litellm_chat_client

        return create_litellm_chat_client(
            model=model_override or self.llm.llm_model,
            timeout=60.0,
        )

    def create_supervisor_llm(self, model_override: str | None = None) -> Any:
        """Create an OpenAI-shaped supervisor client without LangChain wrappers."""
        return self.create_llm(model_override=model_override)

    def create_embeddings(self) -> Any:
        """Create BGEM3Embeddings instance."""
        from src.runtime.integrations.embeddings import BGEM3Embeddings

        return BGEM3Embeddings(
            base_url=self.retrieval.bge_m3_url,
            timeout=self.retrieval.bge_m3_timeout,
        )

    def create_sparse_embeddings(self) -> Any:
        """Create BGEM3SparseEmbeddings instance."""
        from src.runtime.integrations.embeddings import BGEM3SparseEmbeddings

        return BGEM3SparseEmbeddings(
            base_url=self.retrieval.bge_m3_url,
            timeout=self.retrieval.bge_m3_timeout,
        )


# Auto-generate flat @property accessors from _FLAT_KWARGS.
# This replaces hundreds of manually written getter/setter pairs (#2577).
for _flat_name, (_sub_attr, _sub_field) in _FLAT_KWARGS.items():
    setattr(GraphConfig, _flat_name, _make_flat_property(_sub_attr, _sub_field))


__all__ = [
    "_FLAT_KWARGS",
    "CacheConfig",
    "DomainConfig",
    "GraphConfig",
    "LlmConfig",
    "ResponseConfig",
    "RetrievalConfig",
    "SecurityConfig",
    "VoiceConfig",
]
