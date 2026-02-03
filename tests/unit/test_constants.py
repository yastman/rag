"""Unit tests for src/config/constants.py."""

from src.config.constants import (
    DEFAULTS,
    RATE_LIMITS,
    APIProvider,
    BatchSizes,
    HSNWParameters,
    MetricValues,
    MMRParameters,
    ModelName,
    RetrievalStages,
    SearchEngine,
    ThresholdValues,
    VectorDimensions,
)


class TestSearchEngine:
    """Test SearchEngine enum."""

    def test_search_engine_values(self):
        """Test all search engine values."""
        assert SearchEngine.BASELINE.value == "baseline"
        assert SearchEngine.HYBRID_RRF.value == "hybrid_rrf"
        assert SearchEngine.HYBRID_RRF_COLBERT.value == "hybrid_rrf_colbert"
        assert SearchEngine.DBSF_COLBERT.value == "dbsf_colbert"

    def test_search_engine_is_string_enum(self):
        """Test that SearchEngine is a string enum."""
        assert isinstance(SearchEngine.BASELINE, str)
        assert SearchEngine.BASELINE == "baseline"

    def test_search_engine_from_string(self):
        """Test creating SearchEngine from string."""
        engine = SearchEngine("hybrid_rrf_colbert")
        assert engine == SearchEngine.HYBRID_RRF_COLBERT


class TestAPIProvider:
    """Test APIProvider enum."""

    def test_api_provider_values(self):
        """Test all API provider values."""
        assert APIProvider.CLAUDE.value == "claude"
        assert APIProvider.OPENAI.value == "openai"
        assert APIProvider.GROQ.value == "groq"
        assert APIProvider.Z_AI.value == "zai"

    def test_api_provider_is_string_enum(self):
        """Test that APIProvider is a string enum."""
        assert isinstance(APIProvider.CLAUDE, str)
        assert APIProvider.OPENAI == "openai"

    def test_api_provider_from_string(self):
        """Test creating APIProvider from string."""
        provider = APIProvider("claude")
        assert provider == APIProvider.CLAUDE


class TestModelName:
    """Test ModelName enum."""

    def test_claude_models(self):
        """Test Claude model names."""
        assert "claude-3-opus" in ModelName.CLAUDE_OPUS.value
        assert "claude-3-5-sonnet" in ModelName.CLAUDE_SONNET.value
        assert "claude-3-5-haiku" in ModelName.CLAUDE_HAIKU.value

    def test_openai_models(self):
        """Test OpenAI model names."""
        assert "gpt-4-turbo" in ModelName.GPT_4_TURBO.value
        assert ModelName.GPT_4.value == "gpt-4"
        assert ModelName.GPT_35_TURBO.value == "gpt-3.5-turbo"

    def test_groq_models(self):
        """Test Groq model names."""
        assert "llama3-70b" in ModelName.GROQ_LLAMA3_70B.value
        assert "llama3-8b" in ModelName.GROQ_LLAMA3_8B.value
        assert "mixtral" in ModelName.GROQ_MIXTRAL.value


class TestVectorDimensions:
    """Test VectorDimensions dataclass."""

    def test_vector_dimensions(self):
        """Test vector dimension values."""
        assert VectorDimensions.DENSE == 1024
        assert VectorDimensions.COLBERT == 1024
        assert VectorDimensions.FULL == 1024


class TestThresholdValues:
    """Test ThresholdValues dataclass."""

    def test_threshold_values(self):
        """Test threshold values."""
        assert ThresholdValues.DENSE_ONLY == 0.5
        assert ThresholdValues.HYBRID == 0.3
        assert ThresholdValues.COLBERT == 0.4
        assert ThresholdValues.MINIMUM == 0.1

    def test_dense_higher_than_hybrid(self):
        """Test that dense-only threshold is higher than hybrid."""
        assert ThresholdValues.DENSE_ONLY > ThresholdValues.HYBRID


class TestHSNWParameters:
    """Test HSNWParameters dataclass."""

    def test_hsnw_ef_values(self):
        """Test HNSW ef parameter values."""
        assert HSNWParameters.EF_DEFAULT == 128
        assert HSNWParameters.EF_HIGH_PRECISION == 256
        assert HSNWParameters.EF_LOW_LATENCY == 64
        assert HSNWParameters.MAX_CONNECTIONS == 16

    def test_ef_ordering(self):
        """Test that EF values are properly ordered."""
        assert (
            HSNWParameters.EF_LOW_LATENCY
            < HSNWParameters.EF_DEFAULT
            < HSNWParameters.EF_HIGH_PRECISION
        )


class TestBatchSizes:
    """Test BatchSizes dataclass."""

    def test_batch_sizes(self):
        """Test batch size values."""
        assert BatchSizes.QUERIES == 10
        assert BatchSizes.EMBEDDINGS == 32
        assert BatchSizes.DOCUMENTS == 16
        assert BatchSizes.CONTEXT == 5


class TestRetrievalStages:
    """Test RetrievalStages dataclass."""

    def test_retrieval_stages(self):
        """Test retrieval stage values."""
        assert RetrievalStages.STAGE1_CANDIDATES == 100
        assert RetrievalStages.STAGE2_FINAL == 10

    def test_stage1_larger_than_stage2(self):
        """Test that stage 1 retrieves more than stage 2."""
        assert RetrievalStages.STAGE1_CANDIDATES > RetrievalStages.STAGE2_FINAL


class TestMetricValues:
    """Test MetricValues dataclass."""

    def test_metric_k_values(self):
        """Test metric K values."""
        assert MetricValues.RECALL_K == [1, 3, 5, 10]
        assert MetricValues.NDCG_K == [1, 3, 5, 10]
        assert MetricValues.FAILURE_K == [1, 3, 5, 10]


class TestMMRParameters:
    """Test MMRParameters dataclass."""

    def test_mmr_parameters(self):
        """Test MMR parameter values."""
        assert MMRParameters.LAMBDA == 0.5
        assert MMRParameters.ENABLED is True


class TestDefaults:
    """Test DEFAULTS dictionary."""

    def test_defaults_contains_search_engine(self):
        """Test that defaults contains search engine."""
        assert "search_engine" in DEFAULTS
        assert DEFAULTS["search_engine"] == SearchEngine.HYBRID_RRF_COLBERT

    def test_defaults_contains_api_provider(self):
        """Test that defaults contains API provider."""
        assert "api_provider" in DEFAULTS
        assert DEFAULTS["api_provider"] == APIProvider.CLAUDE

    def test_defaults_contains_model(self):
        """Test that defaults contains model."""
        assert "model" in DEFAULTS
        assert DEFAULTS["model"] == ModelName.CLAUDE_SONNET

    def test_defaults_contains_retry_config(self):
        """Test that defaults contains retry config."""
        assert "max_retries" in DEFAULTS
        assert "retry_backoff" in DEFAULTS
        assert DEFAULTS["max_retries"] == 3
        assert DEFAULTS["retry_backoff"] == 2


class TestRateLimits:
    """Test RATE_LIMITS dictionary."""

    def test_rate_limits_all_providers(self):
        """Test rate limits for all providers."""
        assert APIProvider.CLAUDE in RATE_LIMITS
        assert APIProvider.OPENAI in RATE_LIMITS
        assert APIProvider.GROQ in RATE_LIMITS
        assert APIProvider.Z_AI in RATE_LIMITS

    def test_groq_fastest(self):
        """Test that Groq has fastest rate limit."""
        assert RATE_LIMITS[APIProvider.GROQ] < RATE_LIMITS[APIProvider.CLAUDE]
        assert RATE_LIMITS[APIProvider.GROQ] < RATE_LIMITS[APIProvider.OPENAI]
