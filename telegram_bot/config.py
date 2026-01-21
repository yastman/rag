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
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "contextual_bulgaria")

    # LLM (OpenAI compatible API - Cerebras Qwen 3 32B)
    llm_api_key: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.cerebras.ai/v1")
    llm_model: str = os.getenv("LLM_MODEL", "qwen-3-32b")

    # RAG settings
    top_k: int = 5
    min_score: float = 0.3  # Lower threshold for better recall with filters

    # CESC Configuration (Contextual Extraction and Storage of Conversation)
    cesc_enabled: bool = os.getenv("CESC_ENABLED", "true").lower() == "true"
    cesc_extraction_frequency: int = int(os.getenv("CESC_EXTRACTION_FREQUENCY", "3"))
    user_context_ttl: int = int(os.getenv("USER_CONTEXT_TTL", str(30 * 24 * 3600)))
