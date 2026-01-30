"""Bot configuration."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass
class BotConfig:
    """Telegram bot configuration."""

    # Telegram
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Services
    bge_m3_url: str = os.getenv("BGE_M3_URL", "http://localhost:8000")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: Optional[str] = os.getenv("QDRANT_API_KEY") or None
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4")

    # LLM (OpenAI compatible API - GLM-4)
    llm_api_key: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.cerebras.ai/v1")
    llm_model: str = os.getenv("LLM_MODEL", "zai-glm-4.7")

    # RAG settings
    top_k: int = 5
    min_score: float = 0.3  # Lower threshold for better recall with filters

    ***REMOVED*** AI Configuration
    voyage_api_key: str = os.getenv("VOYAGE_API_KEY", "")
    # Asymmetric retrieval: documents use large model, queries use lite model
    voyage_model_docs: str = os.getenv("VOYAGE_MODEL_DOCS", "voyage-4-large")
    voyage_model_queries: str = os.getenv("VOYAGE_MODEL_QUERIES", "voyage-4-lite")
    voyage_model_rerank: str = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2.5")
    # Matryoshka embedding dimensions (2048, 1024, 512, 256)
    # Lower dimensions = less storage, faster search, slightly lower quality
    voyage_embedding_dim: int = int(os.getenv("VOYAGE_EMBEDDING_DIM", "1024"))

    # Legacy (for backward compatibility)
    voyage_embed_model: str = os.getenv("VOYAGE_EMBED_MODEL", "voyage-3-large")
    voyage_cache_model: str = os.getenv("VOYAGE_CACHE_MODEL", "voyage-3-lite")
    voyage_rerank_model: str = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2")

    # Search Configuration
    # 2026 best practice: fewer chunks in LLM context = faster generation
    search_top_k: int = int(os.getenv("SEARCH_TOP_K", "20"))  # Reduced from 50->30->20
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "3"))  # Reduced from 5

    # CESC Configuration (Contextual Extraction and Storage of Conversation)
    cesc_enabled: bool = os.getenv("CESC_ENABLED", "true").lower() == "true"
    cesc_extraction_frequency: int = int(os.getenv("CESC_EXTRACTION_FREQUENCY", "3"))
    user_context_ttl: int = int(os.getenv("USER_CONTEXT_TTL", str(30 * 24 * 3600)))

    # BM42 Sparse Embedding Service
    bm42_url: str = os.getenv("BM42_URL", "http://localhost:8002")

    # Hybrid Search Configuration
    hybrid_dense_weight: float = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.6"))
    hybrid_sparse_weight: float = float(os.getenv("HYBRID_SPARSE_WEIGHT", "0.4"))

    # Score Boosting Configuration
    freshness_boost_enabled: bool = os.getenv("FRESHNESS_BOOST", "false").lower() == "true"
    freshness_field: str = os.getenv("FRESHNESS_FIELD", "created_at")
    freshness_scale_days: int = int(os.getenv("FRESHNESS_SCALE_DAYS", "30"))

    # MMR Diversity Configuration (disabled by default - Voyage rerank is sufficient)
    # Enable only for diversity-focused use cases via MMR_ENABLED=true
    mmr_enabled: bool = os.getenv("MMR_ENABLED", "false").lower() == "true"
    mmr_lambda: float = float(os.getenv("MMR_LAMBDA", "0.7"))

    ***REMOVED*** Quantization Configuration (2026 best practice)
    # Binary quantization: 40x faster, -75% RAM for dim >= 1024
    qdrant_use_quantization: bool = os.getenv("QDRANT_USE_QUANTIZATION", "true").lower() == "true"
    qdrant_quantization_rescore: bool = (
        os.getenv("QDRANT_QUANTIZATION_RESCORE", "true").lower() == "true"
    )
    qdrant_quantization_oversampling: float = float(
        os.getenv("QDRANT_QUANTIZATION_OVERSAMPLING", "2.0")
    )
    qdrant_quantization_always_ram: bool = (
        os.getenv("QDRANT_QUANTIZATION_ALWAYS_RAM", "true").lower() == "true"
    )
