"""GraphConfig — configuration for the imperative RAG runtime.

Moved from ``telegram_bot/graph/config.py`` as the second slice of the
reverse-layering fix tracked under #1948 / #2045 / #2049. The legacy
``telegram_bot.graph.config`` module is kept as a thin re-export so
existing imports across the test suite, ``telegram_bot/`` internals, and
external consumers continue to work without churn.

Provides service factories for LLM, embeddings, and cache thresholds.

#2482: GraphConfig is now a composition of focused config classes.
Flat attribute access (e.g. ``config.llm_model``) is preserved via
``@property`` for full backward compatibility with existing callers.
The constructor also accepts legacy flat kwargs so existing call-sites
like ``GraphConfig(llm_model="x", bge_m3_url="y")`` continue to work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LlmConfig:
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


@dataclass
class RetrievalConfig:
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


@dataclass
class CacheConfig:
    """Redis cache thresholds and TTLs."""

    cache_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "FAQ": 0.12,
            "ENTITY": 0.10,
            "GENERAL": 0.08,
            "STRUCTURED": 0.05,
        }
    )
    cache_ttl: dict[str, int] = field(
        default_factory=lambda: {
            "FAQ": 86400,  # 24h
            "ENTITY": 3600,  # 1h
            "GENERAL": 3600,  # 1h
            "STRUCTURED": 7200,  # 2h
        }
    )


@dataclass
class DomainConfig:
    """Domain identity and language settings."""

    domain: str = "недвижимость"
    domain_language: str = "ru"


@dataclass
class ResponseConfig:
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


@dataclass
class VoiceConfig:
    """Voice transcription settings."""

    # Voice transcription (#151)
    show_transcription: bool = True
    voice_language: str = "ru"
    stt_model: str = "whisper"


@dataclass
class SecurityConfig:
    """Guard and content filter settings."""

    # Prompt injection defense (#226)
    guard_mode: str = "hard"  # "hard" = block, "soft" = flag + continue, "log" = log only
    # Content filtering (#227)
    content_filter_enabled: bool = True


# Mapping from legacy flat kwarg name -> (sub_config_attr, sub_config_field)
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


@dataclass(init=False)
class GraphConfig:
    """Configuration for the imperative RAG runtime.

    Composed from focused sub-config classes (#2482). Flat attribute
    access (e.g. ``config.llm_model``, ``config.domain``) is preserved
    via ``@property`` for backward compatibility with all existing callers.
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

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — LLM                      #
    # ------------------------------------------------------------------ #

    @property
    def llm_base_url(self) -> str:
        return self.llm.llm_base_url

    @llm_base_url.setter
    def llm_base_url(self, v: str) -> None:
        self.llm.llm_base_url = v

    @property
    def llm_api_key(self) -> str:
        return self.llm.llm_api_key

    @llm_api_key.setter
    def llm_api_key(self, v: str) -> None:
        self.llm.llm_api_key = v

    @property
    def llm_model(self) -> str:
        return self.llm.llm_model

    @llm_model.setter
    def llm_model(self, v: str) -> None:
        self.llm.llm_model = v

    @property
    def llm_temperature(self) -> float:
        return self.llm.llm_temperature

    @llm_temperature.setter
    def llm_temperature(self, v: float) -> None:
        self.llm.llm_temperature = v

    @property
    def llm_max_tokens(self) -> int:
        return self.llm.llm_max_tokens

    @llm_max_tokens.setter
    def llm_max_tokens(self, v: int) -> None:
        self.llm.llm_max_tokens = v

    @property
    def generate_max_tokens(self) -> int:
        return self.llm.generate_max_tokens

    @generate_max_tokens.setter
    def generate_max_tokens(self, v: int) -> None:
        self.llm.generate_max_tokens = v

    @property
    def reasoning_effort(self) -> str | None:
        return self.llm.reasoning_effort

    @reasoning_effort.setter
    def reasoning_effort(self, v: str | None) -> None:
        self.llm.reasoning_effort = v

    @property
    def reasoning_format(self) -> str | None:
        return self.llm.reasoning_format

    @reasoning_format.setter
    def reasoning_format(self, v: str | None) -> None:
        self.llm.reasoning_format = v

    @property
    def disable_reasoning(self) -> bool | None:
        return self.llm.disable_reasoning

    @disable_reasoning.setter
    def disable_reasoning(self, v: bool | None) -> None:
        self.llm.disable_reasoning = v

    @property
    def rewrite_model(self) -> str:
        return self.llm.rewrite_model

    @rewrite_model.setter
    def rewrite_model(self, v: str) -> None:
        self.llm.rewrite_model = v

    @property
    def rewrite_max_tokens(self) -> int:
        return self.llm.rewrite_max_tokens

    @rewrite_max_tokens.setter
    def rewrite_max_tokens(self, v: int) -> None:
        self.llm.rewrite_max_tokens = v

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — Retrieval                #
    # ------------------------------------------------------------------ #

    @property
    def bge_m3_url(self) -> str:
        return self.retrieval.bge_m3_url

    @bge_m3_url.setter
    def bge_m3_url(self, v: str) -> None:
        self.retrieval.bge_m3_url = v

    @property
    def bge_m3_timeout(self) -> float:
        return self.retrieval.bge_m3_timeout

    @bge_m3_timeout.setter
    def bge_m3_timeout(self, v: float) -> None:
        self.retrieval.bge_m3_timeout = v

    @property
    def qdrant_url(self) -> str:
        return self.retrieval.qdrant_url

    @qdrant_url.setter
    def qdrant_url(self, v: str) -> None:
        self.retrieval.qdrant_url = v

    @property
    def qdrant_collection(self) -> str:
        return self.retrieval.qdrant_collection

    @qdrant_collection.setter
    def qdrant_collection(self, v: str) -> None:
        self.retrieval.qdrant_collection = v

    @property
    def search_top_k(self) -> int:
        return self.retrieval.search_top_k

    @search_top_k.setter
    def search_top_k(self, v: int) -> None:
        self.retrieval.search_top_k = v

    @property
    def rerank_top_k(self) -> int:
        return self.retrieval.rerank_top_k

    @rerank_top_k.setter
    def rerank_top_k(self, v: int) -> None:
        self.retrieval.rerank_top_k = v

    @property
    def redis_url(self) -> str:
        return self.retrieval.redis_url

    @redis_url.setter
    def redis_url(self, v: str) -> None:
        self.retrieval.redis_url = v

    @property
    def max_rewrite_attempts(self) -> int:
        return self.retrieval.max_rewrite_attempts

    @max_rewrite_attempts.setter
    def max_rewrite_attempts(self, v: int) -> None:
        self.retrieval.max_rewrite_attempts = v

    @property
    def skip_rerank_threshold(self) -> float:
        return self.retrieval.skip_rerank_threshold

    @skip_rerank_threshold.setter
    def skip_rerank_threshold(self, v: float) -> None:
        self.retrieval.skip_rerank_threshold = v

    @property
    def relevance_threshold_rrf(self) -> float:
        return self.retrieval.relevance_threshold_rrf

    @relevance_threshold_rrf.setter
    def relevance_threshold_rrf(self, v: float) -> None:
        self.retrieval.relevance_threshold_rrf = v

    @property
    def score_improvement_delta(self) -> float:
        return self.retrieval.score_improvement_delta

    @score_improvement_delta.setter
    def score_improvement_delta(self, v: float) -> None:
        self.retrieval.score_improvement_delta = v

    @property
    def rerank_provider(self) -> str:
        return self.retrieval.rerank_provider

    @rerank_provider.setter
    def rerank_provider(self, v: str) -> None:
        self.retrieval.rerank_provider = v

    @property
    def small_to_big_mode(self) -> str:
        return self.retrieval.small_to_big_mode

    @small_to_big_mode.setter
    def small_to_big_mode(self, v: str) -> None:
        self.retrieval.small_to_big_mode = v

    @property
    def small_to_big_window_before(self) -> int:
        return self.retrieval.small_to_big_window_before

    @small_to_big_window_before.setter
    def small_to_big_window_before(self, v: int) -> None:
        self.retrieval.small_to_big_window_before = v

    @property
    def small_to_big_window_after(self) -> int:
        return self.retrieval.small_to_big_window_after

    @small_to_big_window_after.setter
    def small_to_big_window_after(self, v: int) -> None:
        self.retrieval.small_to_big_window_after = v

    @property
    def max_expanded_chunks(self) -> int:
        return self.retrieval.max_expanded_chunks

    @max_expanded_chunks.setter
    def max_expanded_chunks(self, v: int) -> None:
        self.retrieval.max_expanded_chunks = v

    @property
    def max_context_tokens(self) -> int:
        return self.retrieval.max_context_tokens

    @max_context_tokens.setter
    def max_context_tokens(self, v: int) -> None:
        self.retrieval.max_context_tokens = v

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — Cache                    #
    # ------------------------------------------------------------------ #

    @property
    def cache_thresholds(self) -> dict[str, float]:
        return self.cache.cache_thresholds

    @cache_thresholds.setter
    def cache_thresholds(self, v: dict[str, float]) -> None:
        self.cache.cache_thresholds = v

    @property
    def cache_ttl(self) -> dict[str, int]:
        return self.cache.cache_ttl

    @cache_ttl.setter
    def cache_ttl(self, v: dict[str, int]) -> None:
        self.cache.cache_ttl = v

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — Domain                   #
    # ------------------------------------------------------------------ #
    # ``domain_cfg`` holds the DomainConfig object.  Callers expect
    # ``config.domain`` to be a string; the property below provides that.

    @property
    def domain(self) -> str:
        return self.domain_cfg.domain

    @domain.setter
    def domain(self, v: str) -> None:
        self.domain_cfg.domain = v

    @property
    def domain_language(self) -> str:
        return self.domain_cfg.domain_language

    @domain_language.setter
    def domain_language(self, v: str) -> None:
        self.domain_cfg.domain_language = v

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — Response                 #
    # ------------------------------------------------------------------ #

    @property
    def response_style_enabled(self) -> bool:
        return self.response.response_style_enabled

    @response_style_enabled.setter
    def response_style_enabled(self, v: bool) -> None:
        self.response.response_style_enabled = v

    @property
    def response_style_shadow_mode(self) -> bool:
        return self.response.response_style_shadow_mode

    @response_style_shadow_mode.setter
    def response_style_shadow_mode(self, v: bool) -> None:
        self.response.response_style_shadow_mode = v

    @property
    def show_sources(self) -> bool:
        return self.response.show_sources

    @show_sources.setter
    def show_sources(self, v: bool) -> None:
        self.response.show_sources = v

    @property
    def streaming_enabled(self) -> bool:
        return self.response.streaming_enabled

    @streaming_enabled.setter
    def streaming_enabled(self, v: bool) -> None:
        self.response.streaming_enabled = v

    @property
    def ttft_drift_warn_ms(self) -> int:
        return self.response.ttft_drift_warn_ms

    @ttft_drift_warn_ms.setter
    def ttft_drift_warn_ms(self, v: int) -> None:
        self.response.ttft_drift_warn_ms = v

    @property
    def classifier_mode(self) -> str:
        return self.response.classifier_mode

    @classifier_mode.setter
    def classifier_mode(self, v: str) -> None:
        self.response.classifier_mode = v

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — Voice                    #
    # ------------------------------------------------------------------ #

    @property
    def show_transcription(self) -> bool:
        return self.voice.show_transcription

    @show_transcription.setter
    def show_transcription(self, v: bool) -> None:
        self.voice.show_transcription = v

    @property
    def voice_language(self) -> str:
        return self.voice.voice_language

    @voice_language.setter
    def voice_language(self, v: str) -> None:
        self.voice.voice_language = v

    @property
    def stt_model(self) -> str:
        return self.voice.stt_model

    @stt_model.setter
    def stt_model(self, v: str) -> None:
        self.voice.stt_model = v

    # ------------------------------------------------------------------ #
    # Backward-compatible flat property access — Security                 #
    # ------------------------------------------------------------------ #

    @property
    def guard_mode(self) -> str:
        return self.security.guard_mode

    @guard_mode.setter
    def guard_mode(self, v: str) -> None:
        self.security.guard_mode = v

    @property
    def content_filter_enabled(self) -> bool:
        return self.security.content_filter_enabled

    @content_filter_enabled.setter
    def content_filter_enabled(self, v: bool) -> None:
        self.security.content_filter_enabled = v

    # ------------------------------------------------------------------ #
    # Reasoning helper                                                     #
    # ------------------------------------------------------------------ #

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        """Return SDK-shaped reasoning params for chat.completions.create().

        ``reasoning_effort`` is part of the OpenAI Python SDK chat completions
        schema. Provider-specific LiteLLM/Cerebras/Z.ai controls must travel in
        ``extra_body`` so the OpenAI-compatible client does not reject them as
        unexpected top-level kwargs.
        """
        return self.llm.get_reasoning_kwargs()

    # ------------------------------------------------------------------ #
    # from_env classmethod                                                 #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_env(cls) -> GraphConfig:
        """Create GraphConfig from environment variables."""
        llm = LlmConfig(
            llm_api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            rewrite_model=os.getenv("REWRITE_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini")),
            rewrite_max_tokens=int(os.getenv("REWRITE_MAX_TOKENS", "64")),
            generate_max_tokens=int(os.getenv("GENERATE_MAX_TOKENS", "1024")),
            reasoning_effort=os.getenv("REASONING_EFFORT") or None,
            reasoning_format=os.getenv("REASONING_FORMAT") or None,
            disable_reasoning=(
                os.getenv("DISABLE_REASONING", "").lower() == "true"
                if os.getenv("DISABLE_REASONING")
                else None
            ),
        )
        retrieval = RetrievalConfig(
            bge_m3_url=os.getenv("BGE_M3_URL", "http://bge-m3:8000"),
            bge_m3_timeout=float(os.getenv("BGE_M3_TIMEOUT", "120.0")),
            qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge"),
            search_top_k=int(os.getenv("SEARCH_TOP_K", "40")),
            rerank_top_k=int(os.getenv("RERANK_TOP_K", "7")),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379"),
            max_rewrite_attempts=int(os.getenv("MAX_REWRITE_ATTEMPTS", "1")),
            skip_rerank_threshold=float(os.getenv("SKIP_RERANK_THRESHOLD", "0.018")),
            relevance_threshold_rrf=float(os.getenv("RELEVANCE_THRESHOLD_RRF", "0.005")),
            score_improvement_delta=float(os.getenv("SCORE_IMPROVEMENT_DELTA", "0.001")),
            rerank_provider=os.getenv("RERANK_PROVIDER", "colbert"),
            small_to_big_mode=os.getenv("SMALL_TO_BIG_MODE", "on"),
            small_to_big_window_before=int(os.getenv("SMALL_TO_BIG_WINDOW_BEFORE", "0")),
            small_to_big_window_after=int(os.getenv("SMALL_TO_BIG_WINDOW_AFTER", "2")),
            max_expanded_chunks=int(os.getenv("MAX_EXPANDED_CHUNKS", "10")),
            max_context_tokens=int(os.getenv("MAX_CONTEXT_TOKENS", "8000")),
        )
        domain_cfg = DomainConfig(
            domain=os.getenv("BOT_DOMAIN", "недвижимость"),
            domain_language=os.getenv("BOT_LANGUAGE", "ru"),
        )
        response = ResponseConfig(
            streaming_enabled=os.getenv("STREAMING_ENABLED", "true").lower() == "true",
            response_style_enabled=os.getenv("RESPONSE_STYLE_ENABLED", "false").lower() == "true",
            response_style_shadow_mode=os.getenv("RESPONSE_STYLE_SHADOW_MODE", "false").lower()
            == "true",
            show_sources=os.getenv("SHOW_SOURCES", "false").lower() == "true",
            ttft_drift_warn_ms=int(os.getenv("TTFT_DRIFT_WARN_MS", "500")),
            classifier_mode=os.getenv("CLASSIFIER_MODE", "regex"),
        )
        voice = VoiceConfig(
            show_transcription=os.getenv("SHOW_TRANSCRIPTION", "true").lower() == "true",
            voice_language=os.getenv("VOICE_LANGUAGE", "ru"),
            stt_model=os.getenv("STT_MODEL", "whisper"),
        )
        security = SecurityConfig(
            guard_mode=os.getenv("GUARD_MODE", "hard"),
            content_filter_enabled=os.getenv("CONTENT_FILTER_ENABLED", "true").lower() == "true",
        )
        return cls(
            llm=llm,
            retrieval=retrieval,
            cache=CacheConfig(),
            domain_cfg=domain_cfg,
            response=response,
            voice=voice,
            security=security,
        )

    # ------------------------------------------------------------------ #
    # Service factories                                                    #
    # ------------------------------------------------------------------ #

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


__all__ = [
    "CacheConfig",
    "DomainConfig",
    "GraphConfig",
    "LlmConfig",
    "ResponseConfig",
    "RetrievalConfig",
    "SecurityConfig",
    "VoiceConfig",
]
