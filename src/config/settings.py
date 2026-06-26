"""Configuration settings for Contextual RAG Pipeline."""

import os
from pathlib import Path
from typing import Any

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
from .qdrant_policy import resolve_collection_name


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
        env_file: str | None = None,
        # API Configuration
        api_provider: str | None = None,
        anthropic_api_key: str | None = None,
        openai_api_key: str | None = None,
        groq_api_key: str | None = None,
        # Model Configuration
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        # Vector Database
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        # Paths
        data_dir: str | None = None,
        docs_dir: str | None = None,
        logs_dir: str | None = None,
        # Search Configuration
        search_engine: str | None = None,
        score_threshold: float | None = None,
        top_k: int | None = None,
        # Processing
        batch_size_embeddings: int | None = None,
        batch_size_documents: int | None = None,
        # Retry
        max_retries: int | None = None,
        retry_backoff: float | None = None,
    ):
        """Initialize settings from environment and arguments."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        self._load_api_config(api_provider, anthropic_api_key, openai_api_key, groq_api_key)
        self._load_model_config(model_name, temperature, max_tokens, max_retries, retry_backoff)
        self._load_qdrant_config(qdrant_url, qdrant_api_key)
        self._load_paths(data_dir, docs_dir, logs_dir)
        self._load_search_config(
            search_engine, score_threshold, top_k, batch_size_embeddings, batch_size_documents
        )
        self._load_features()
        self._load_quantization_config()
        self._load_small_to_big_config()
        self._load_acorn_config()
        self._load_hyde_config()
        self._load_env_config()

    def _load_api_config(
        self,
        api_provider: str | None,
        anthropic_api_key: str | None,
        openai_api_key: str | None,
        groq_api_key: str | None,
    ) -> None:
        default_provider = DEFAULTS["api_provider"]
        default_provider_value = (
            default_provider.value
            if isinstance(default_provider, APIProvider)
            else str(default_provider)
        )
        self.api_provider = APIProvider(
            api_provider or os.getenv("API_PROVIDER") or default_provider_value
        )
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self._validate_api_keys()

    def _load_model_config(
        self,
        model_name: str | None,
        temperature: float | None,
        max_tokens: int | None,
        max_retries: int | None,
        retry_backoff: float | None,
    ) -> None:
        self.model_name = model_name or os.getenv(
            "MODEL_NAME",
            self._default_model_for_provider(self.api_provider),
        )
        self.temperature = temperature if temperature is not None else 0.0
        self.max_tokens = max_tokens or 4096
        self.max_retries = max_retries or DEFAULTS["max_retries"]
        self.retry_backoff = retry_backoff or DEFAULTS["retry_backoff"]

    def _load_qdrant_config(self, qdrant_url: str | None, qdrant_api_key: str | None) -> None:
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY", "")

    def _load_paths(self, data_dir: str | None, docs_dir: str | None, logs_dir: str | None) -> None:
        self.project_root = Path(__file__).parent.parent.parent
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR") or self.project_root / "data")
        self.docs_dir = Path(docs_dir or os.getenv("DOCS_DIR") or self.project_root / "docs")
        self.logs_dir = Path(logs_dir or os.getenv("LOGS_DIR") or self.project_root / "logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _load_search_config(
        self,
        search_engine: str | None,
        score_threshold: float | None,
        top_k: int | None,
        batch_size_embeddings: int | None,
        batch_size_documents: int | None,
    ) -> None:
        default_engine = DEFAULTS["search_engine"]
        default_engine_value = (
            default_engine.value
            if isinstance(default_engine, SearchEngine)
            else str(default_engine)
        )
        self.search_engine = SearchEngine(
            search_engine or os.getenv("SEARCH_ENGINE") or default_engine_value
        )
        self.score_threshold = score_threshold or 0.3
        self.top_k = top_k or 10
        self.collection_name = os.getenv("COLLECTION_NAME") or DEFAULT_COLLECTION
        self.batch_size_embeddings = batch_size_embeddings or BatchSizes.EMBEDDINGS
        self.batch_size_documents = batch_size_documents or BatchSizes.DOCUMENTS
        self.batch_size_queries = BatchSizes.QUERIES
        self.retrieval_stage1_candidates = RetrievalStages.STAGE1_CANDIDATES
        self.retrieval_stage2_final = RetrievalStages.STAGE2_FINAL

    def _load_features(self) -> None:
        self.enable_caching = os.getenv("ENABLE_CACHING", "true").lower() == "true"
        self.enable_query_expansion = os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"

    def _load_quantization_config(self) -> None:
        # Binary: 32x compression, 40x faster (best for dim >= 1024)
        # Scalar (INT8): 4x compression, better accuracy
        self.quantization_mode = QuantizationMode(os.getenv("QUANTIZATION_MODE", "binary").lower())
        self.quantization_rescore = os.getenv("QUANTIZATION_RESCORE", "true").lower() == "true"
        self.quantization_oversampling = float(os.getenv("QUANTIZATION_OVERSAMPLING", "2.0"))

    def _load_small_to_big_config(self) -> None:
        # Mode: off (disabled), on (always expand), auto (expand for complex queries)
        self.small_to_big_mode = os.getenv("SMALL_TO_BIG_MODE", "off").lower()
        # Window size: number of chunks to fetch before/after each result
        self.small_to_big_window_before = int(os.getenv("SMALL_TO_BIG_WINDOW_BEFORE", "1"))
        self.small_to_big_window_after = int(os.getenv("SMALL_TO_BIG_WINDOW_AFTER", "1"))
        # Limits to prevent context explosion
        self.max_expanded_chunks = int(os.getenv("MAX_EXPANDED_CHUNKS", "10"))
        self.max_context_tokens = int(os.getenv("MAX_CONTEXT_TOKENS", "8000"))

    def _load_acorn_config(self) -> None:
        # ACORN improves search quality when strict filters cause graph disconnection
        # Best for: low selectivity filters (< 40% of vectors match)
        # Requires: qdrant-client >= 1.15.0
        self.acorn_mode = AcornMode(os.getenv("ACORN_MODE", "off").lower())
        # max_selectivity: ACORN won't be used if selectivity > this value (0.0-1.0)
        self.acorn_max_selectivity = float(os.getenv("ACORN_MAX_SELECTIVITY", "0.4"))
        # In 'auto' mode: enable ACORN only if estimated selectivity < this threshold
        self.acorn_enabled_selectivity_threshold = float(
            os.getenv("ACORN_ENABLED_SELECTIVITY_THRESHOLD", "0.4")
        )

    def _load_hyde_config(self) -> None:
        # When enabled, generates hypothetical answer for short queries (< 5 words)
        self.use_hyde = os.getenv("USE_HYDE", "false").lower() == "true"
        # Minimum query length to skip HyDE (longer queries don't benefit as much)
        self.hyde_min_words = int(os.getenv("HYDE_MIN_WORDS", "5"))

    def _load_env_config(self) -> None:
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
        return resolve_collection_name(self.collection_name, self.quantization_mode.value)

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
            "use_hyde": self.use_hyde,
            "hyde_min_words": self.hyde_min_words,
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
