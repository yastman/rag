"""Constants for Contextual RAG Pipeline."""

from dataclasses import dataclass
from enum import StrEnum


class QuantizationMode(StrEnum):
    """Qdrant vector quantization modes.

    Controls which collection suffix to use:
    - OFF: base collection (no quantization or quantization_ignore=True)
    - SCALAR: *_scalar collection (INT8, 4x compression, better accuracy)
    - BINARY: *_binary collection (binary, 32x compression, fastest)
    """

    OFF = "off"
    SCALAR = "scalar"
    BINARY = "binary"


class SearchEngine(StrEnum):
    """Available search engine implementations."""

    BASELINE = "baseline"  # Dense vectors only
    HYBRID_RRF = "hybrid_rrf"  # Dense + Sparse with RRF fusion
    HYBRID_RRF_COLBERT = "hybrid_rrf_colbert"  # Dense + Sparse + ColBERT (Variant A - BEST)
    DBSF_COLBERT = "dbsf_colbert"  # Density-Based Semantic Fusion + ColBERT


class SmallToBigMode(StrEnum):
    """Small-to-big context expansion mode."""

    OFF = "off"  # No expansion
    ON = "on"  # Always expand
    AUTO = "auto"  # Expand only for complex queries


class AcornMode(StrEnum):
    """ACORN search mode for filtered queries.

    ACORN (Agnostic Contiguous Optimized Retrieval Network) improves
    filtered vector search by using second-hop exploration to avoid
    graph disconnection problems in HNSW.

    Best for: filters with low selectivity (< 40% of vectors match).

    Modes:
    - OFF: Never use ACORN (default)
    - ON: Always use ACORN when filters present
    - AUTO: Use ACORN only when selectivity < threshold
    """

    OFF = "off"  # Never use ACORN
    ON = "on"  # Always use ACORN with filters
    AUTO = "auto"  # Use ACORN only with low selectivity filters


class APIProvider(StrEnum):
    """Available LLM API providers."""

    CLAUDE = "claude"  # Anthropic Claude (recommended)
    OPENAI = "openai"  # OpenAI GPT
    GROQ = "groq"  # Groq LLaMA (fast)
    # Legacy providers (deprecated)
    Z_AI = "zai"  # Z.AI GLM (legacy, not recommended)


class ModelName(StrEnum):
    """LLM model names by provider."""

    # Anthropic Claude
    CLAUDE_OPUS = "claude-3-opus-20240229"
    CLAUDE_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_HAIKU = "claude-3-5-haiku-20241022"

    # OpenAI
    GPT_4_TURBO = "gpt-4-turbo-preview"
    GPT_4 = "gpt-4"
    GPT_35_TURBO = "gpt-3.5-turbo"

    # Groq
    GROQ_LLAMA3_70B = "llama3-70b-8192"
    GROQ_LLAMA3_8B = "llama3-8b-8192"
    GROQ_MIXTRAL = "mixtral-8x7b-32768"


@dataclass
class VectorDimensions:
    """Vector dimension sizes for embeddings."""

    DENSE = 1024  # BGE-M3 dense vectors
    COLBERT = 1024  # ColBERT sparse dimension
    FULL = 1024  # Full embedding dimension


@dataclass
class ThresholdValues:
    """Score thresholds for filtering search results."""

    DENSE_ONLY = 0.5  # For dense-only search
    HYBRID = 0.3  # For DBSF fusion (more lenient)
    COLBERT = 0.4  # For ColBERT reranking
    MINIMUM = 0.1  # Absolute minimum for any result


@dataclass
class HSNWParameters:
    """HNSW (Hierarchical Navigable Small World) search parameters."""

    EF_DEFAULT = 128  # Default HNSW ef parameter
    EF_HIGH_PRECISION = 256  # Higher precision, slower
    EF_LOW_LATENCY = 64  # Faster, lower precision
    MAX_CONNECTIONS = 16  # Maximum connections per point


@dataclass
class BatchSizes:
    """Batch processing sizes."""

    QUERIES = 10  # Number of queries to batch
    EMBEDDINGS = 32  # Number of texts to embed at once
    DOCUMENTS = 16  # Number of documents in ingestion
    CONTEXT = 5  # Number of chunks for contextualization


@dataclass
class RetrievalStages:
    """Multi-stage retrieval limits."""

    STAGE1_CANDIDATES = 100  # Dense+Sparse fusion candidates
    STAGE2_FINAL = 10  # Final results after reranking


@dataclass
class MetricValues:
    """Evaluation metric configurations."""

    RECALL_K = [1, 3, 5, 10]
    NDCG_K = [1, 3, 5, 10]
    FAILURE_K = [1, 3, 5, 10]


@dataclass
class MMRParameters:
    """Maximum Marginal Relevance parameters."""

    LAMBDA = 0.5  # Balance: 1.0 (relevance) to 0.0 (diversity)
    ENABLED = True


# Rate limiting (seconds between API calls)
RATE_LIMITS = {
    APIProvider.CLAUDE: 1.2,
    APIProvider.OPENAI: 1.2,
    APIProvider.GROQ: 0.5,  # Groq is faster
    APIProvider.Z_AI: 1.2,  # Legacy
}

# API limits (tokens, requests/min, etc.)
API_LIMITS = {
    APIProvider.CLAUDE: {
        "max_tokens": 4096,
        "context_window": 200000,
        "requests_per_minute": 50,
    },
    APIProvider.OPENAI: {
        "max_tokens": 4096,
        "context_window": 128000,
        "requests_per_minute": 3500,
    },
    APIProvider.GROQ: {
        "max_tokens": 8192,
        "context_window": 8192,
        "requests_per_minute": 30,
    },
}

# Default values
DEFAULTS = {
    "search_engine": SearchEngine.HYBRID_RRF_COLBERT,  # Variant A - Best performance
    "api_provider": APIProvider.CLAUDE,
    "model": ModelName.CLAUDE_SONNET,
    "temperature": 0.0,
    "max_retries": 3,
    "retry_backoff": 2,
}

# Collection names
COLLECTIONS = {
    "legal_documents": "legal_documents",  # Main unified collection
    "legacy_civil": "uk_civil_code_v2",  # Deprecated
    "legacy_contextual": "uk_civil_code_contextual_kg",  # Deprecated
}

# Default collection
DEFAULT_COLLECTION = "legal_documents"
