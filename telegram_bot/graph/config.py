"""GraphConfig — configuration for LangGraph RAG pipeline.

Provides service factories for LLM, embeddings, and cache thresholds.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphConfig:
    """Configuration for the RAG LangGraph pipeline."""

    llm_base_url: str = "http://litellm:4000"
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

    bge_m3_url: str = "http://bge-m3:8000"
    bge_m3_timeout: float = 120.0

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "gdrive_documents_bge"
    search_top_k: int = 20

    redis_url: str = "redis://redis:6379"

    domain: str = "недвижимость"
    domain_language: str = "ru"

    max_rewrite_attempts: int = 1
    # RRF score scale: 1/(rank+k), k=60 default. Top-1 = ~0.016, Top-20 last = ~0.012.
    # skip_rerank_threshold >= 0.018 means top-1 result already has very high rank — safe to skip
    # ColBERT rerank. Must be > 1/61≈0.016 to ensure ColBERT runs on borderline cases.
    skip_rerank_threshold: float = 0.018
    # RRF score scale: threshold 0.005 accepts all top-20 results (~0.012..0.016 typical range).
    # This is intentional — loose filter that only rejects truly irrelevant results (score < 0.005).
    relevance_threshold_rrf: float = 0.005
    score_improvement_delta: float = 0.001
    streaming_enabled: bool = True
    rerank_provider: str = "colbert"
    # Response length control rollout (#129)
    response_style_enabled: bool = False
    response_style_shadow_mode: bool = False
    # Source attribution (#225)
    show_sources: bool = False
    # Content filtering (#227)
    content_filter_enabled: bool = True
    # Voice transcription (#151)
    show_transcription: bool = True
    voice_language: str = "ru"
    stt_model: str = "whisper"
    # Prompt injection defense (#226)
    guard_mode: str = "hard"  # "hard" = block, "soft" = flag + continue, "log" = log only
    guard_ml_enabled: bool = False  # opt-in ML classifier layer (llm-guard)
    llm_guard_url: str = "http://llm-guard:8100"  # URL of llm-guard Docker service
    # TTFT drift warning threshold in ms (#675); raise for reasoning models behind proxy
    ttft_drift_warn_ms: int = 500

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

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        """Return non-None reasoning params for chat.completions.create()."""
        kwargs: dict[str, Any] = {}
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.reasoning_format is not None:
            kwargs["reasoning_format"] = self.reasoning_format
        if self.disable_reasoning is not None:
            kwargs["disable_reasoning"] = self.disable_reasoning
        return kwargs

    @classmethod
    def from_env(cls) -> GraphConfig:
        """Create GraphConfig from environment variables."""
        return cls(
            llm_base_url=os.getenv("LLM_BASE_URL", "http://litellm:4000"),
            llm_api_key=os.getenv(
                "LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")
            ),  # LLM_API_KEY preferred
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            rewrite_model=os.getenv("REWRITE_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini")),
            rewrite_max_tokens=int(os.getenv("REWRITE_MAX_TOKENS", "64")),
            generate_max_tokens=int(os.getenv("GENERATE_MAX_TOKENS", "1024")),
            bge_m3_url=os.getenv("BGE_M3_URL", "http://bge-m3:8000"),
            bge_m3_timeout=float(os.getenv("BGE_M3_TIMEOUT", "120.0")),
            qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge"),
            search_top_k=int(os.getenv("SEARCH_TOP_K", "20")),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379"),
            domain=os.getenv("BOT_DOMAIN", "недвижимость"),
            domain_language=os.getenv("BOT_LANGUAGE", "ru"),
            max_rewrite_attempts=int(os.getenv("MAX_REWRITE_ATTEMPTS", "1")),
            skip_rerank_threshold=float(os.getenv("SKIP_RERANK_THRESHOLD", "0.018")),
            relevance_threshold_rrf=float(os.getenv("RELEVANCE_THRESHOLD_RRF", "0.005")),
            score_improvement_delta=float(os.getenv("SCORE_IMPROVEMENT_DELTA", "0.001")),
            streaming_enabled=os.getenv("STREAMING_ENABLED", "true").lower() == "true",
            rerank_provider=os.getenv("RERANK_PROVIDER", "colbert"),
            response_style_enabled=os.getenv("RESPONSE_STYLE_ENABLED", "false").lower() == "true",
            response_style_shadow_mode=os.getenv("RESPONSE_STYLE_SHADOW_MODE", "false").lower()
            == "true",
            show_sources=os.getenv("SHOW_SOURCES", "false").lower() == "true",
            content_filter_enabled=os.getenv("CONTENT_FILTER_ENABLED", "true").lower() == "true",
            show_transcription=os.getenv("SHOW_TRANSCRIPTION", "true").lower() == "true",
            voice_language=os.getenv("VOICE_LANGUAGE", "ru"),
            stt_model=os.getenv("STT_MODEL", "whisper"),
            guard_mode=os.getenv("GUARD_MODE", "hard"),
            guard_ml_enabled=os.getenv("GUARD_ML_ENABLED", "false").lower() == "true",
            llm_guard_url=os.getenv("LLM_GUARD_URL", "http://llm-guard:8100"),
            ttft_drift_warn_ms=int(os.getenv("TTFT_DRIFT_WARN_MS", "500")),
            reasoning_effort=os.getenv("REASONING_EFFORT") or None,
            reasoning_format=os.getenv("REASONING_FORMAT") or None,
            disable_reasoning=(
                os.getenv("DISABLE_REASONING", "").lower() == "true"
                if os.getenv("DISABLE_REASONING")
                else None
            ),
        )

    def create_llm(self, model_override: str | None = None) -> Any:
        """Create AsyncOpenAI client for graph nodes that call chat.completions."""
        from langfuse.openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=self.llm_api_key or "no-key",
            base_url=self.llm_base_url,
            max_retries=2,
            timeout=60.0,
        )

    def create_supervisor_llm(self, model_override: str | None = None) -> Any:
        """Create LangChain chat model for supervisor graph tool routing."""
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=model_override or self.llm_model,
            api_key=SecretStr(self.llm_api_key or "no-key"),
            base_url=self.llm_base_url,
        )

    def create_embeddings(self) -> Any:
        """Create BGEM3Embeddings instance."""
        from telegram_bot.integrations.embeddings import BGEM3Embeddings

        return BGEM3Embeddings(
            base_url=self.bge_m3_url,
            timeout=self.bge_m3_timeout,
        )

    def create_sparse_embeddings(self) -> Any:
        """Create BGEM3SparseEmbeddings instance."""
        from telegram_bot.integrations.embeddings import BGEM3SparseEmbeddings

        return BGEM3SparseEmbeddings(
            base_url=self.bge_m3_url,
            timeout=self.bge_m3_timeout,
        )

    def create_hybrid_embeddings(self) -> Any:
        """Create BGEM3HybridEmbeddings instance."""
        from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

        return BGEM3HybridEmbeddings(
            base_url=self.bge_m3_url,
            timeout=self.bge_m3_timeout,
        )
