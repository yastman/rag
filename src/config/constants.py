"""Constants for Contextual RAG Pipeline."""

from dataclasses import dataclass
from enum import Enum


class QuantizationMode(str, Enum):
    """Qdrant vector quantization modes.

    Controls which collection suffix to use:
    - OFF: base collection (no quantization or quantization_ignore=True)
    - SCALAR: *_scalar collection (INT8, 4x compression, better accuracy)
    - BINARY: *_binary collection (binary, 32x compression, fastest)
    """

    OFF = "off"
    SCALAR = "scalar"
    BINARY = "binary"


class SearchEngine(str, Enum):
    """Available search engine implementations."""

    BASELINE = "baseline"  ***REMOVED*** Dense vectors only
    HYBRID_RRF = "hybrid_rrf"  ***REMOVED*** Dense + Sparse with RRF fusion
    HYBRID_RRF_COLBERT = "hybrid_rrf_colbert"  ***REMOVED*** Dense + Sparse + ColBERT (Variant A - BEST)
    DBSF_COLBERT = "dbsf_colbert"  ***REMOVED*** Density-Based Semantic Fusion + ColBERT


class SmallToBigMode(str, Enum):
    """Small-to-big context expansion mode."""

    OFF = "off"  ***REMOVED*** No expansion
    ON = "on"  ***REMOVED*** Always expand
    AUTO = "auto"  ***REMOVED*** Expand only for complex queries


class APIProvider(str, Enum):
    """Available LLM API providers."""

    CLAUDE = "claude"  ***REMOVED*** Anthropic Claude (recommended)
    OPENAI = "openai"  ***REMOVED*** OpenAI GPT
    GROQ = "groq"  ***REMOVED*** Groq LLaMA (fast)
    ***REMOVED*** Legacy providers (deprecated)
    Z_AI = "zai"  ***REMOVED*** Z.AI GLM (legacy, not recommended)


class ModelName(str, Enum):
    """LLM model names by provider."""

    ***REMOVED*** Anthropic Claude
    CLAUDE_OPUS = "claude-3-opus-20240229"
    CLAUDE_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_HAIKU = "claude-3-5-haiku-20241022"

    ***REMOVED*** OpenAI
    GPT_4_TURBO = "gpt-4-turbo-preview"
    GPT_4 = "gpt-4"
    GPT_35_TURBO = "gpt-3.5-turbo"

    ***REMOVED*** Groq
    GROQ_LLAMA3_70B = "llama3-70b-8192"
    GROQ_LLAMA3_8B = "llama3-8b-8192"
    GROQ_MIXTRAL = "mixtral-8x7b-32768"


@dataclass
class VectorDimensions:
    """Vector dimension sizes for embeddings."""

    DENSE = 1024  ***REMOVED*** BGE-M3 dense vectors
    COLBERT = 1024  ***REMOVED*** ColBERT sparse dimension
    FULL = 1024  ***REMOVED*** Full embedding dimension


@dataclass
class ThresholdValues:
    """Score thresholds for filtering search results."""

    DENSE_ONLY = 0.5  ***REMOVED*** For dense-only search
    HYBRID = 0.3  ***REMOVED*** For DBSF fusion (more lenient)
    COLBERT = 0.4  ***REMOVED*** For ColBERT reranking
    MINIMUM = 0.1  ***REMOVED*** Absolute minimum for any result


@dataclass
class HSNWParameters:
    """HNSW (Hierarchical Navigable Small World) search parameters."""

    EF_DEFAULT = 128  ***REMOVED*** Default HNSW ef parameter
    EF_HIGH_PRECISION = 256  ***REMOVED*** Higher precision, slower
    EF_LOW_LATENCY = 64  ***REMOVED*** Faster, lower precision
    MAX_CONNECTIONS = 16  ***REMOVED*** Maximum connections per point


@dataclass
class BatchSizes:
    """Batch processing sizes."""

    QUERIES = 10  ***REMOVED*** Number of queries to batch
    EMBEDDINGS = 32  ***REMOVED*** Number of texts to embed at once
    DOCUMENTS = 16  ***REMOVED*** Number of documents in ingestion
    CONTEXT = 5  ***REMOVED*** Number of chunks for contextualization


@dataclass
class RetrievalStages:
    """Multi-stage retrieval limits."""

    STAGE1_CANDIDATES = 100  ***REMOVED*** Dense+Sparse fusion candidates
    STAGE2_FINAL = 10  ***REMOVED*** Final results after reranking


@dataclass
class MetricValues:
    """Evaluation metric configurations."""

    RECALL_K = [1, 3, 5, 10]
    NDCG_K = [1, 3, 5, 10]
    FAILURE_K = [1, 3, 5, 10]


@dataclass
class MMRParameters:
    """Maximum Marginal Relevance parameters."""

    LAMBDA = 0.5  ***REMOVED*** Balance: 1.0 (relevance) to 0.0 (diversity)
    ENABLED = True


***REMOVED*** Rate limiting (seconds between API calls)
RATE_LIMITS = {
    APIProvider.CLAUDE: 1.2,
    APIProvider.OPENAI: 1.2,
    APIProvider.GROQ: 0.5,  ***REMOVED*** Groq is faster
    APIProvider.Z_AI: 1.2,  ***REMOVED*** Legacy
}

***REMOVED*** API limits (tokens, requests/min, etc.)
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

***REMOVED*** Default values
DEFAULTS = {
    "search_engine": SearchEngine.HYBRID_RRF_COLBERT,  ***REMOVED*** Variant A - Best performance
    "api_provider": APIProvider.CLAUDE,
    "model": ModelName.CLAUDE_SONNET,
    "temperature": 0.0,
    "max_retries": 3,
    "retry_backoff": 2,
}

***REMOVED*** Collection names
COLLECTIONS = {
    "legal_documents": "legal_documents",  ***REMOVED*** Main unified collection
    "legacy_civil": "uk_civil_code_v2",  ***REMOVED*** Deprecated
    "legacy_contextual": "uk_civil_code_contextual_kg",  ***REMOVED*** Deprecated
}

***REMOVED*** Default collection
DEFAULT_COLLECTION = "legal_documents"
