"""Unit tests for src/config/constants.py module.

Tests verify:
- Constants exist and have expected values
- Enums have correct members
- Dataclass attributes are correct types
- Dictionary constants have expected structure
"""

from dataclasses import is_dataclass

import pytest

from src.config.constants import (
    API_LIMITS,
    COLLECTIONS,
    DEFAULT_COLLECTION,
    DEFAULTS,
    # Dictionary constants
    RATE_LIMITS,
    APIProvider,
    BatchSizes,
    HSNWParameters,
    MetricValues,
    MMRParameters,
    ModelName,
    RetrievalStages,
    # Enums
    SearchEngine,
    ThresholdValues,
    # Dataclasses
    VectorDimensions,
)


class TestSearchEngineEnum:
    """Tests for SearchEngine enum."""

    def test_search_engine_has_all_members(self):
        """Verify SearchEngine has all expected members."""
        expected_members = {"BASELINE", "HYBRID_RRF", "HYBRID_RRF_COLBERT", "DBSF_COLBERT"}
        actual_members = {member.name for member in SearchEngine}
        assert actual_members == expected_members

    def test_search_engine_values(self):
        """Verify SearchEngine values are correct strings."""
        assert SearchEngine.BASELINE.value == "baseline"
        assert SearchEngine.HYBRID_RRF.value == "hybrid_rrf"
        assert SearchEngine.HYBRID_RRF_COLBERT.value == "hybrid_rrf_colbert"
        assert SearchEngine.DBSF_COLBERT.value == "dbsf_colbert"

    def test_search_engine_is_str_enum(self):
        """Verify SearchEngine inherits from str."""
        assert isinstance(SearchEngine.BASELINE, str)
        assert SearchEngine.BASELINE == "baseline"

    def test_search_engine_string_comparison(self):
        """Verify SearchEngine members can be compared as strings."""
        assert SearchEngine.HYBRID_RRF_COLBERT == "hybrid_rrf_colbert"
        # str() returns the enum repr, but value gives the string value
        assert SearchEngine.HYBRID_RRF_COLBERT.value == "hybrid_rrf_colbert"


class TestAPIProviderEnum:
    """Tests for APIProvider enum."""

    def test_api_provider_has_all_members(self):
        """Verify APIProvider has all expected members."""
        expected_members = {"CLAUDE", "OPENAI", "GROQ", "Z_AI"}
        actual_members = {member.name for member in APIProvider}
        assert actual_members == expected_members

    def test_api_provider_values(self):
        """Verify APIProvider values are correct strings."""
        assert APIProvider.CLAUDE.value == "claude"
        assert APIProvider.OPENAI.value == "openai"
        assert APIProvider.GROQ.value == "groq"
        assert APIProvider.Z_AI.value == "zai"

    def test_api_provider_is_str_enum(self):
        """Verify APIProvider inherits from str."""
        assert isinstance(APIProvider.CLAUDE, str)
        assert APIProvider.CLAUDE == "claude"


class TestModelNameEnum:
    """Tests for ModelName enum."""

    def test_model_name_has_claude_models(self):
        """Verify ModelName has Anthropic Claude models."""
        claude_models = {"CLAUDE_OPUS", "CLAUDE_SONNET", "CLAUDE_HAIKU"}
        actual_members = {member.name for member in ModelName}
        assert claude_models.issubset(actual_members)

    def test_model_name_has_openai_models(self):
        """Verify ModelName has OpenAI models."""
        openai_models = {"GPT_4_TURBO", "GPT_4", "GPT_35_TURBO"}
        actual_members = {member.name for member in ModelName}
        assert openai_models.issubset(actual_members)

    def test_model_name_has_groq_models(self):
        """Verify ModelName has Groq models."""
        groq_models = {"GROQ_LLAMA3_70B", "GROQ_LLAMA3_8B", "GROQ_MIXTRAL"}
        actual_members = {member.name for member in ModelName}
        assert groq_models.issubset(actual_members)

    def test_model_name_values_are_valid_strings(self):
        """Verify ModelName values are non-empty strings."""
        for model in ModelName:
            assert isinstance(model.value, str)
            assert len(model.value) > 0

    def test_claude_model_values(self):
        """Verify Claude model identifiers."""
        assert "claude" in ModelName.CLAUDE_OPUS.value.lower()
        assert "claude" in ModelName.CLAUDE_SONNET.value.lower()
        assert "claude" in ModelName.CLAUDE_HAIKU.value.lower()

    def test_gpt_model_values(self):
        """Verify GPT model identifiers."""
        assert "gpt" in ModelName.GPT_4_TURBO.value.lower()
        assert "gpt" in ModelName.GPT_4.value.lower()
        assert "gpt" in ModelName.GPT_35_TURBO.value.lower()

    def test_groq_model_values(self):
        """Verify Groq model identifiers include known models."""
        assert "llama" in ModelName.GROQ_LLAMA3_70B.value.lower()
        assert "mixtral" in ModelName.GROQ_MIXTRAL.value.lower()


class TestVectorDimensions:
    """Tests for VectorDimensions dataclass."""

    def test_is_dataclass(self):
        """Verify VectorDimensions is a dataclass."""
        assert is_dataclass(VectorDimensions)

    def test_dense_dimension(self):
        """Verify DENSE dimension value."""
        assert VectorDimensions.DENSE == 1024
        assert isinstance(VectorDimensions.DENSE, int)

    def test_colbert_dimension(self):
        """Verify COLBERT dimension value."""
        assert VectorDimensions.COLBERT == 1024
        assert isinstance(VectorDimensions.COLBERT, int)

    def test_full_dimension(self):
        """Verify FULL dimension value."""
        assert VectorDimensions.FULL == 1024
        assert isinstance(VectorDimensions.FULL, int)

    def test_dimensions_are_positive(self):
        """Verify all dimensions are positive integers."""
        assert VectorDimensions.DENSE > 0
        assert VectorDimensions.COLBERT > 0
        assert VectorDimensions.FULL > 0


class TestThresholdValues:
    """Tests for ThresholdValues dataclass."""

    def test_is_dataclass(self):
        """Verify ThresholdValues is a dataclass."""
        assert is_dataclass(ThresholdValues)

    def test_threshold_values(self):
        """Verify threshold values are correct."""
        assert ThresholdValues.DENSE_ONLY == 0.5
        assert ThresholdValues.HYBRID == 0.3
        assert ThresholdValues.COLBERT == 0.4
        assert ThresholdValues.MINIMUM == 0.1

    def test_thresholds_are_floats(self):
        """Verify thresholds are numeric (int or float)."""
        assert isinstance(ThresholdValues.DENSE_ONLY, (int, float))
        assert isinstance(ThresholdValues.HYBRID, (int, float))
        assert isinstance(ThresholdValues.COLBERT, (int, float))
        assert isinstance(ThresholdValues.MINIMUM, (int, float))

    def test_thresholds_are_valid_range(self):
        """Verify thresholds are in valid range [0, 1]."""
        assert 0 <= ThresholdValues.DENSE_ONLY <= 1
        assert 0 <= ThresholdValues.HYBRID <= 1
        assert 0 <= ThresholdValues.COLBERT <= 1
        assert 0 <= ThresholdValues.MINIMUM <= 1

    def test_minimum_is_lowest(self):
        """Verify MINIMUM is the lowest threshold."""
        all_thresholds = [
            ThresholdValues.DENSE_ONLY,
            ThresholdValues.HYBRID,
            ThresholdValues.COLBERT,
            ThresholdValues.MINIMUM,
        ]
        assert min(all_thresholds) == ThresholdValues.MINIMUM


class TestHSNWParameters:
    """Tests for HSNWParameters dataclass."""

    def test_is_dataclass(self):
        """Verify HSNWParameters is a dataclass."""
        assert is_dataclass(HSNWParameters)

    def test_ef_default_value(self):
        """Verify EF_DEFAULT value."""
        assert HSNWParameters.EF_DEFAULT == 128

    def test_ef_high_precision_value(self):
        """Verify EF_HIGH_PRECISION value."""
        assert HSNWParameters.EF_HIGH_PRECISION == 256

    def test_ef_low_latency_value(self):
        """Verify EF_LOW_LATENCY value."""
        assert HSNWParameters.EF_LOW_LATENCY == 64

    def test_max_connections_value(self):
        """Verify MAX_CONNECTIONS value."""
        assert HSNWParameters.MAX_CONNECTIONS == 16

    def test_ef_ordering(self):
        """Verify EF parameters are ordered correctly."""
        assert HSNWParameters.EF_LOW_LATENCY < HSNWParameters.EF_DEFAULT
        assert HSNWParameters.EF_DEFAULT < HSNWParameters.EF_HIGH_PRECISION

    def test_all_values_are_positive_integers(self):
        """Verify all HSNW parameters are positive integers."""
        assert isinstance(HSNWParameters.EF_DEFAULT, int) and HSNWParameters.EF_DEFAULT > 0
        assert (
            isinstance(HSNWParameters.EF_HIGH_PRECISION, int)
            and HSNWParameters.EF_HIGH_PRECISION > 0
        )
        assert isinstance(HSNWParameters.EF_LOW_LATENCY, int) and HSNWParameters.EF_LOW_LATENCY > 0
        assert (
            isinstance(HSNWParameters.MAX_CONNECTIONS, int) and HSNWParameters.MAX_CONNECTIONS > 0
        )


class TestBatchSizes:
    """Tests for BatchSizes dataclass."""

    def test_is_dataclass(self):
        """Verify BatchSizes is a dataclass."""
        assert is_dataclass(BatchSizes)

    def test_batch_values(self):
        """Verify batch size values."""
        assert BatchSizes.QUERIES == 10
        assert BatchSizes.EMBEDDINGS == 32
        assert BatchSizes.DOCUMENTS == 16
        assert BatchSizes.CONTEXT == 5

    def test_all_values_are_positive_integers(self):
        """Verify all batch sizes are positive integers."""
        assert isinstance(BatchSizes.QUERIES, int) and BatchSizes.QUERIES > 0
        assert isinstance(BatchSizes.EMBEDDINGS, int) and BatchSizes.EMBEDDINGS > 0
        assert isinstance(BatchSizes.DOCUMENTS, int) and BatchSizes.DOCUMENTS > 0
        assert isinstance(BatchSizes.CONTEXT, int) and BatchSizes.CONTEXT > 0


class TestRetrievalStages:
    """Tests for RetrievalStages dataclass."""

    def test_is_dataclass(self):
        """Verify RetrievalStages is a dataclass."""
        assert is_dataclass(RetrievalStages)

    def test_stage_values(self):
        """Verify retrieval stage values."""
        assert RetrievalStages.STAGE1_CANDIDATES == 100
        assert RetrievalStages.STAGE2_FINAL == 10

    def test_stage1_greater_than_stage2(self):
        """Verify stage 1 candidates > stage 2 final (makes sense for filtering)."""
        assert RetrievalStages.STAGE1_CANDIDATES > RetrievalStages.STAGE2_FINAL

    def test_all_values_are_positive_integers(self):
        """Verify stage values are positive integers."""
        assert (
            isinstance(RetrievalStages.STAGE1_CANDIDATES, int)
            and RetrievalStages.STAGE1_CANDIDATES > 0
        )
        assert isinstance(RetrievalStages.STAGE2_FINAL, int) and RetrievalStages.STAGE2_FINAL > 0


class TestMetricValues:
    """Tests for MetricValues dataclass."""

    def test_is_dataclass(self):
        """Verify MetricValues is a dataclass."""
        assert is_dataclass(MetricValues)

    def test_recall_k_values(self):
        """Verify RECALL_K values."""
        assert MetricValues.RECALL_K == [1, 3, 5, 10]

    def test_ndcg_k_values(self):
        """Verify NDCG_K values."""
        assert MetricValues.NDCG_K == [1, 3, 5, 10]

    def test_failure_k_values(self):
        """Verify FAILURE_K values."""
        assert MetricValues.FAILURE_K == [1, 3, 5, 10]

    def test_metric_values_are_lists(self):
        """Verify metric values are lists."""
        assert isinstance(MetricValues.RECALL_K, list)
        assert isinstance(MetricValues.NDCG_K, list)
        assert isinstance(MetricValues.FAILURE_K, list)

    def test_metric_values_are_sorted(self):
        """Verify metric K values are sorted ascending."""
        assert sorted(MetricValues.RECALL_K) == MetricValues.RECALL_K
        assert sorted(MetricValues.NDCG_K) == MetricValues.NDCG_K
        assert sorted(MetricValues.FAILURE_K) == MetricValues.FAILURE_K


class TestMMRParameters:
    """Tests for MMRParameters dataclass."""

    def test_is_dataclass(self):
        """Verify MMRParameters is a dataclass."""
        assert is_dataclass(MMRParameters)

    def test_lambda_value(self):
        """Verify LAMBDA value."""
        assert MMRParameters.LAMBDA == 0.5

    def test_enabled_value(self):
        """Verify ENABLED value."""
        assert MMRParameters.ENABLED is True

    def test_lambda_in_valid_range(self):
        """Verify LAMBDA is in valid range [0, 1]."""
        assert 0 <= MMRParameters.LAMBDA <= 1


class TestRateLimits:
    """Tests for RATE_LIMITS dictionary."""

    def test_rate_limits_is_dict(self):
        """Verify RATE_LIMITS is a dictionary."""
        assert isinstance(RATE_LIMITS, dict)

    def test_rate_limits_has_all_providers(self):
        """Verify RATE_LIMITS has entries for all APIProviders."""
        for provider in APIProvider:
            assert provider in RATE_LIMITS

    def test_rate_limits_values_are_positive(self):
        """Verify all rate limits are positive numbers."""
        for provider, limit in RATE_LIMITS.items():
            assert isinstance(limit, (int, float))
            assert limit > 0, f"{provider} has non-positive rate limit"

    def test_groq_is_fastest(self):
        """Verify Groq has the lowest rate limit (fastest)."""
        assert RATE_LIMITS[APIProvider.GROQ] < RATE_LIMITS[APIProvider.CLAUDE]
        assert RATE_LIMITS[APIProvider.GROQ] < RATE_LIMITS[APIProvider.OPENAI]


class TestAPILimits:
    """Tests for API_LIMITS dictionary."""

    def test_api_limits_is_dict(self):
        """Verify API_LIMITS is a dictionary."""
        assert isinstance(API_LIMITS, dict)

    def test_api_limits_has_expected_providers(self):
        """Verify API_LIMITS has entries for main providers."""
        expected_providers = {APIProvider.CLAUDE, APIProvider.OPENAI, APIProvider.GROQ}
        for provider in expected_providers:
            assert provider in API_LIMITS

    def test_api_limits_structure(self):
        """Verify each provider has required keys."""
        required_keys = {"max_tokens", "context_window", "requests_per_minute"}
        for provider, limits in API_LIMITS.items():
            assert isinstance(limits, dict)
            for key in required_keys:
                assert key in limits, f"{provider} missing {key}"

    def test_api_limits_values_are_positive(self):
        """Verify all API limits are positive integers."""
        for provider, limits in API_LIMITS.items():
            for key, value in limits.items():
                assert isinstance(value, int)
                assert value > 0, f"{provider}.{key} is not positive"

    def test_claude_has_largest_context(self):
        """Verify Claude has the largest context window."""
        claude_context = API_LIMITS[APIProvider.CLAUDE]["context_window"]
        openai_context = API_LIMITS[APIProvider.OPENAI]["context_window"]
        groq_context = API_LIMITS[APIProvider.GROQ]["context_window"]
        assert claude_context >= openai_context
        assert claude_context >= groq_context


class TestDefaults:
    """Tests for DEFAULTS dictionary."""

    def test_defaults_is_dict(self):
        """Verify DEFAULTS is a dictionary."""
        assert isinstance(DEFAULTS, dict)

    def test_defaults_has_required_keys(self):
        """Verify DEFAULTS has all required keys."""
        required_keys = {
            "search_engine",
            "api_provider",
            "model",
            "temperature",
            "max_retries",
            "retry_backoff",
        }
        for key in required_keys:
            assert key in DEFAULTS, f"Missing required key: {key}"

    def test_default_search_engine(self):
        """Verify default search engine is HYBRID_RRF_COLBERT (best performance)."""
        assert DEFAULTS["search_engine"] == SearchEngine.HYBRID_RRF_COLBERT

    def test_default_api_provider(self):
        """Verify default API provider is Claude."""
        assert DEFAULTS["api_provider"] == APIProvider.CLAUDE

    def test_default_model(self):
        """Verify default model is Claude Sonnet."""
        assert DEFAULTS["model"] == ModelName.CLAUDE_SONNET

    def test_default_temperature(self):
        """Verify default temperature is 0.0 (deterministic)."""
        assert DEFAULTS["temperature"] == 0.0

    def test_default_max_retries(self):
        """Verify default max retries is positive."""
        assert DEFAULTS["max_retries"] == 3
        assert DEFAULTS["max_retries"] > 0

    def test_default_retry_backoff(self):
        """Verify default retry backoff is positive."""
        assert DEFAULTS["retry_backoff"] == 2
        assert DEFAULTS["retry_backoff"] > 0


class TestCollections:
    """Tests for COLLECTIONS dictionary."""

    def test_collections_is_dict(self):
        """Verify COLLECTIONS is a dictionary."""
        assert isinstance(COLLECTIONS, dict)

    def test_collections_has_legal_documents(self):
        """Verify COLLECTIONS has legal_documents entry."""
        assert "legal_documents" in COLLECTIONS
        assert COLLECTIONS["legal_documents"] == "legal_documents"

    def test_collections_values_are_strings(self):
        """Verify all collection names are non-empty strings."""
        for key, value in COLLECTIONS.items():
            assert isinstance(key, str) and len(key) > 0
            assert isinstance(value, str) and len(value) > 0

    def test_default_collection_exists(self):
        """Verify DEFAULT_COLLECTION exists in COLLECTIONS values."""
        assert DEFAULT_COLLECTION in COLLECTIONS.values()

    def test_default_collection_is_legal_documents(self):
        """Verify DEFAULT_COLLECTION is legal_documents."""
        assert DEFAULT_COLLECTION == "legal_documents"


class TestConstantsIntegration:
    """Integration tests verifying relationships between constants."""

    def test_default_search_engine_is_valid_enum(self):
        """Verify default search engine is a valid SearchEngine member."""
        assert DEFAULTS["search_engine"] in SearchEngine

    def test_default_provider_is_valid_enum(self):
        """Verify default provider is a valid APIProvider member."""
        assert DEFAULTS["api_provider"] in APIProvider

    def test_default_model_is_valid_enum(self):
        """Verify default model is a valid ModelName member."""
        assert DEFAULTS["model"] in ModelName

    def test_rate_limits_match_api_providers(self):
        """Verify RATE_LIMITS keys are APIProvider members."""
        for provider in RATE_LIMITS:
            assert provider in APIProvider

    def test_api_limits_match_api_providers(self):
        """Verify API_LIMITS keys are APIProvider members."""
        for provider in API_LIMITS:
            assert provider in APIProvider

    def test_retrieval_stages_consistent_with_batch_sizes(self):
        """Verify retrieval stages produce reasonable numbers."""
        # Stage 1 candidates should be much larger than final results
        assert RetrievalStages.STAGE1_CANDIDATES >= 10 * RetrievalStages.STAGE2_FINAL

    def test_threshold_values_consistent(self):
        """Verify threshold ordering makes sense for search pipeline."""
        # Hybrid should be more lenient than dense-only (gets more candidates)
        assert ThresholdValues.HYBRID <= ThresholdValues.DENSE_ONLY
        # Minimum should be lowest
        assert ThresholdValues.MINIMUM <= ThresholdValues.HYBRID


class TestEnumMembership:
    """Tests for enum value lookup and membership."""

    def test_search_engine_by_value(self):
        """Verify SearchEngine can be looked up by value."""
        assert SearchEngine("baseline") == SearchEngine.BASELINE
        assert SearchEngine("hybrid_rrf_colbert") == SearchEngine.HYBRID_RRF_COLBERT

    def test_api_provider_by_value(self):
        """Verify APIProvider can be looked up by value."""
        assert APIProvider("claude") == APIProvider.CLAUDE
        assert APIProvider("openai") == APIProvider.OPENAI

    def test_invalid_search_engine_raises_error(self):
        """Verify invalid SearchEngine value raises ValueError."""
        with pytest.raises(ValueError):
            SearchEngine("invalid_engine")

    def test_invalid_api_provider_raises_error(self):
        """Verify invalid APIProvider value raises ValueError."""
        with pytest.raises(ValueError):
            APIProvider("invalid_provider")
