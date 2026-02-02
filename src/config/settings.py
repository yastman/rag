"""Configuration settings for Contextual RAG Pipeline."""

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from .constants import (
    DEFAULT_COLLECTION,
    DEFAULTS,
    AcornMode,
    APIProvider,
    BatchSizes,
    ModelName,
    QuantizationMode,
    RetrievalStages,
    SearchEngine,
)


class Settings:
    """
    Central configuration class for Contextual RAG Pipeline.

    Loads configuration from:
    1. Environment variables (.env file)
    2. Constructor arguments (overrides env vars)
    3. Default values from constants.py

    Example:
        >>> settings = Settings()
        >>> settings.qdrant_url
        'http://localhost:6333'

        >>> settings = Settings(
        ...     api_provider=APIProvider.OPENAI, qdrant_url="https://qdrant.example.com"
        ... )
    """

    def __init__(
        self,
        env_file: Optional[str] = None,
        # API Configuration
        api_provider: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        # Model Configuration
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        # Vector Database
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        # Paths
        data_dir: Optional[str] = None,
        docs_dir: Optional[str] = None,
        logs_dir: Optional[str] = None,
        # Search Configuration
        search_engine: Optional[str] = None,
        score_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
        # Processing
        batch_size_embeddings: Optional[int] = None,
        batch_size_documents: Optional[int] = None,
        # Retry
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
    ):
        """Initialize settings from environment and arguments."""
        # Load .env file first
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        # === API CONFIGURATION ===
        default_provider = DEFAULTS["api_provider"]
        self.api_provider = APIProvider(
            api_provider or os.getenv("API_PROVIDER") or default_provider.value
            if isinstance(default_provider, APIProvider)
            else default_provider
        )
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")

        # Validate that appropriate API key is set
        self._validate_api_keys()

        # === MODEL CONFIGURATION ===
        self.model_name = model_name or os.getenv(
            "MODEL_NAME",
            self._default_model_for_provider(self.api_provider),
        )
        self.temperature = temperature if temperature is not None else 0.0
        self.max_tokens = max_tokens or 4096
        self.max_retries = max_retries or DEFAULTS["max_retries"]
        self.retry_backoff = retry_backoff or DEFAULTS["retry_backoff"]

        # === VECTOR DATABASE ===
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY", "")

        # === PATHS ===
        self.project_root = Path(__file__).parent.parent.parent
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR") or self.project_root / "data")
        self.docs_dir = Path(docs_dir or os.getenv("DOCS_DIR") or self.project_root / "docs")
        self.logs_dir = Path(logs_dir or os.getenv("LOGS_DIR") or self.project_root / "logs")

        # Create directories if they don't exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # === SEARCH CONFIGURATION ===
        default_engine = DEFAULTS["search_engine"]
        self.search_engine = SearchEngine(
            search_engine or os.getenv("SEARCH_ENGINE") or default_engine.value
            if isinstance(default_engine, SearchEngine)
            else default_engine
        )
        self.score_threshold = score_threshold or 0.3
        self.top_k = top_k or 10

        # === COLLECTION ===
        self.collection_name = os.getenv("COLLECTION_NAME") or DEFAULT_COLLECTION

        # === PROCESSING ===
        self.batch_size_embeddings = batch_size_embeddings or BatchSizes.EMBEDDINGS
        self.batch_size_documents = batch_size_documents or BatchSizes.DOCUMENTS
        self.batch_size_queries = BatchSizes.QUERIES

        # === RETRIEVAL STAGES ===
        self.retrieval_stage1_candidates = RetrievalStages.STAGE1_CANDIDATES
        self.retrieval_stage2_final = RetrievalStages.STAGE2_FINAL

        # === FEATURES ===
        self.enable_caching = os.getenv("ENABLE_CACHING", "true").lower() == "true"
        self.enable_query_expansion = os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"
        self.enable_mlflow = os.getenv("ENABLE_MLFLOW", "true").lower() == "true"
        self.enable_langfuse = os.getenv("ENABLE_LANGFUSE", "true").lower() == "true"

        # === QUANTIZATION ===
        # Binary: 32x compression, 40x faster (best for dim >= 1024)
        # Scalar (INT8): 4x compression, better accuracy
        self.quantization_mode = QuantizationMode(
            os.getenv("QUANTIZATION_MODE", "binary").lower()
        )
        self.quantization_rescore = (
            os.getenv("QUANTIZATION_RESCORE", "true").lower() == "true"
        )
        self.quantization_oversampling = float(
            os.getenv("QUANTIZATION_OVERSAMPLING", "2.0")
        )

        # === SMALL-TO-BIG CONTEXT EXPANSION ===
        # Mode: off (disabled), on (always expand), auto (expand for complex queries)
        self.small_to_big_mode = os.getenv("SMALL_TO_BIG_MODE", "off").lower()
        # Window size: number of chunks to fetch before/after each result
        self.small_to_big_window_before = int(os.getenv("SMALL_TO_BIG_WINDOW_BEFORE", "1"))
        self.small_to_big_window_after = int(os.getenv("SMALL_TO_BIG_WINDOW_AFTER", "1"))
        # Limits to prevent context explosion
        self.max_expanded_chunks = int(os.getenv("MAX_EXPANDED_CHUNKS", "10"))
        self.max_context_tokens = int(os.getenv("MAX_CONTEXT_TOKENS", "8000"))

        # === ACORN (Filtered Vector Search Optimization) ===
        # ACORN improves search quality when strict filters cause graph disconnection
        # Best for: low selectivity filters (< 40% of vectors match)
        # Requires: qdrant-client >= 1.15.0
        self.acorn_mode = AcornMode(os.getenv("ACORN_MODE", "off").lower())
        # max_selectivity: ACORN won't be used if selectivity > this value (0.0-1.0)
        # Higher values = more aggressive ACORN usage
        self.acorn_max_selectivity = float(os.getenv("ACORN_MAX_SELECTIVITY", "0.4"))
        # In 'auto' mode: enable ACORN only if estimated selectivity < this threshold
        self.acorn_enabled_selectivity_threshold = float(
            os.getenv("ACORN_ENABLED_SELECTIVITY_THRESHOLD", "0.4")
        )

        # === ENVIRONMENT ===
        self.env = os.getenv("ENV", "development").lower()
        self.debug = os.getenv("DEBUG", "false").lower() == "true"

    def _validate_api_keys(self) -> None:
        """Validate that the required API key is set for the selected provider."""
        if self.api_provider == APIProvider.CLAUDE and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set and API_PROVIDER=claude. "
                "Set ANTHROPIC_API_KEY in .env or use a different provider."
            )
        if self.api_provider == APIProvider.OPENAI and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY not set and API_PROVIDER=openai. "
                "Set OPENAI_API_KEY in .env or use a different provider."
            )
        if self.api_provider == APIProvider.GROQ and not self.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY not set and API_PROVIDER=groq. "
                "Set GROQ_API_KEY in .env or use a different provider."
            )

    @staticmethod
    def _default_model_for_provider(provider: APIProvider) -> str:
        """Get default model name for a provider."""
        defaults = {
            APIProvider.CLAUDE: ModelName.CLAUDE_SONNET.value,
            APIProvider.OPENAI: ModelName.GPT_4_TURBO.value,
            APIProvider.GROQ: ModelName.GROQ_LLAMA3_70B.value,
            APIProvider.Z_AI: "glm-4.6",  # Legacy
        }
        return defaults.get(provider, ModelName.CLAUDE_SONNET.value)

    def get_collection_name(self) -> str:
        """Get collection name based on quantization mode.

        Returns:
            Collection name with appropriate suffix:
            - QuantizationMode.OFF: base collection
            - QuantizationMode.SCALAR: base_scalar
            - QuantizationMode.BINARY: base_binary
        """
        base = self.collection_name
        # Strip existing suffixes
        for suffix in ["_binary", "_scalar"]:
            base = base.removesuffix(suffix)

        if self.quantization_mode == QuantizationMode.SCALAR:
            return f"{base}_scalar"
        if self.quantization_mode == QuantizationMode.BINARY:
            return f"{base}_binary"
        # OFF
        return base

    def to_dict(self) -> dict[str, Any]:
        """Export settings as dictionary (excluding sensitive data)."""
        return {
            "api_provider": self.api_provider.value,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "qdrant_url": self.qdrant_url,
            "collection_name": self.collection_name,
            "search_engine": self.search_engine.value,
            "score_threshold": self.score_threshold,
            "top_k": self.top_k,
            "batch_size_embeddings": self.batch_size_embeddings,
            "batch_size_documents": self.batch_size_documents,
            "enable_caching": self.enable_caching,
            "enable_query_expansion": self.enable_query_expansion,
            "enable_mlflow": self.enable_mlflow,
            "enable_langfuse": self.enable_langfuse,
            "quantization_mode": self.quantization_mode.value,
            "quantization_rescore": self.quantization_rescore,
            "quantization_oversampling": self.quantization_oversampling,
            "small_to_big_mode": self.small_to_big_mode,
            "small_to_big_window_before": self.small_to_big_window_before,
            "small_to_big_window_after": self.small_to_big_window_after,
            "max_expanded_chunks": self.max_expanded_chunks,
            "max_context_tokens": self.max_context_tokens,
            "acorn_mode": self.acorn_mode.value,
            "acorn_max_selectivity": self.acorn_max_selectivity,
            "acorn_enabled_selectivity_threshold": self.acorn_enabled_selectivity_threshold,
            "env": self.env,
            "debug": self.debug,
        }

    def __repr__(self) -> str:
        """String representation of settings."""
        return (
            f"Settings(\n"
            f"  api_provider={self.api_provider.value},\n"
            f"  model={self.model_name},\n"
            f"  search_engine={self.search_engine.value},\n"
            f"  qdrant_url={self.qdrant_url},\n"
            f"  collection={self.collection_name},\n"
            f"  env={self.env}\n"
            f")"
        )


# Lazy settings singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get the global settings instance (lazy initialization).

    Settings are created on first call, not at import time.
    This allows importing the module without requiring API keys.

    Example:
        >>> from src.config.settings import get_settings
        >>> settings = get_settings()
        >>> settings.qdrant_url
        'http://localhost:6333'
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Backward compatibility: settings is now a property-like object
# that creates Settings on first attribute access
class _LazySettings:
    """Lazy proxy for backward compatibility with `from src.config.settings import settings`."""

    _instance: Settings | None = None

    def __getattr__(self, name: str):
        if self._instance is None:
            self._instance = Settings()
        return getattr(self._instance, name)

    def __repr__(self) -> str:
        if self._instance is None:
            return "LazySettings(not initialized)"
        return repr(self._instance)


settings = _LazySettings()
