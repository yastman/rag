"""Bot configuration."""

import os
from dataclasses import dataclass

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
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
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
    # Legacy (for backward compatibility)
    voyage_embed_model: str = os.getenv("VOYAGE_EMBED_MODEL", "voyage-3-large")
    voyage_cache_model: str = os.getenv("VOYAGE_CACHE_MODEL", "voyage-3-lite")
    voyage_rerank_model: str = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2")

    # Search Configuration
    search_top_k: int = int(os.getenv("SEARCH_TOP_K", "50"))
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "5"))

    # CESC Configuration (Contextual Extraction and Storage of Conversation)
    cesc_enabled: bool = os.getenv("CESC_ENABLED", "true").lower() == "true"
    cesc_extraction_frequency: int = int(os.getenv("CESC_EXTRACTION_FREQUENCY", "3"))
    user_context_ttl: int = int(os.getenv("USER_CONTEXT_TTL", str(30 * 24 * 3600)))
