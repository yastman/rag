"""Unit tests for embedding and LLM provider adapters."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import AuthenticationError, RateLimitError, Timeout

from src.adapters.embeddings import (
    LocalBgeM3Provider,
    OpenAIEmbeddingProvider,
    ServiceBgeM3Provider,
    get_embeddings_provider,
)
from src.adapters.llm import (
    LiteLlmProvider,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    get_llm_provider,
)


# 1 factory selects local_bge_m3
def test_factory_selects_local_bge_m3():
    """Verify that get_embeddings_provider selects local_bge_m3 by default."""
    with patch.dict(os.environ, {"EMBEDDINGS_PROVIDER": "local_bge_m3"}):
        provider = get_embeddings_provider()
        assert isinstance(provider, LocalBgeM3Provider)


# 2 unknown provider fails explicitly
def test_factory_unknown_provider_fails():
    """Verify that unknown provider names raise ValueError."""
    with pytest.raises(ValueError, match="Unknown embeddings provider"):
        get_embeddings_provider("unknown_provider_foo")


# 3 no FlagEmbedding import at module import
def test_no_flagembedding_import_at_module_import():
    """Verify that LocalBgeM3Provider can be constructed without importing FlagEmbedding."""
    with patch.dict(sys.modules, {"FlagEmbedding": None}):
        provider = LocalBgeM3Provider()
        assert provider.model_name == "BAAI/bge-m3"


# 4 no model load on __init__
def test_no_model_load_on_init():
    """Verify that BGEM3FlagModel is not instantiated during provider construction."""
    with patch("FlagEmbedding.BGEM3FlagModel") as mock_model_cls:
        _ = LocalBgeM3Provider()
        mock_model_cls.assert_not_called()


# 5 empty embed_texts([]) -> [] no load
@pytest.mark.asyncio
async def test_empty_embed_texts_no_load():
    """Verify that passing an empty list to embed_texts returns empty list without loading model."""
    with patch("FlagEmbedding.BGEM3FlagModel") as mock_model_cls:
        provider = LocalBgeM3Provider()
        result = await provider.embed_texts([])
        assert result == []
        mock_model_cls.assert_not_called()


# 6 first embed_texts() loads lazily and 7 second call reuses model
@pytest.mark.asyncio
async def test_lazy_load_and_reuse_model():
    """Verify that local BGE-M3 model is loaded lazily on first call and reused on second."""
    mock_model = MagicMock()
    mock_model.encode.return_value = {"dense_vecs": [[0.1, 0.2]]}

    with patch("FlagEmbedding.BGEM3FlagModel", return_value=mock_model) as mock_model_cls:
        # Reset singleton state for testing
        import src.adapters.embeddings.local_bge_m3

        src.adapters.embeddings.local_bge_m3._MODEL_INSTANCE = None

        provider = LocalBgeM3Provider()
        mock_model_cls.assert_not_called()

        # First call: triggers load
        res1 = await provider.embed_texts(["hello"])
        assert res1 == [[0.1, 0.2]]
        mock_model_cls.assert_called_once()

        # Second call: reuses loaded singleton
        res2 = await provider.embed_texts(["world"])
        assert res2 == [[0.1, 0.2]]
        mock_model_cls.assert_called_once()


# 8 LiteLlmProvider calls litellm.completion
@pytest.mark.asyncio
async def test_litellm_provider_calls_completion():
    """Verify that LiteLlmProvider.generate calls litellm.acompletion correctly."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "LiteLLM response content"

    with patch("litellm.acompletion", return_value=mock_response) as mock_acompletion:
        provider = LiteLlmProvider(default_model="gpt-4o-mini")
        res = await provider.generate([{"role": "user", "content": "hello"}])
        assert res == "LiteLLM response content"
        mock_acompletion.assert_called_once()
        kwargs = mock_acompletion.call_args[1]
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]


# 9 LiteLLM errors normalized
@pytest.mark.asyncio
async def test_litellm_errors_normalized():
    """Verify that LiteLLM errors are normalized to the unified exception classes."""
    provider = LiteLlmProvider()

    # Auth error
    with patch(
        "litellm.acompletion",
        side_effect=AuthenticationError("auth failed", "openai", "gpt"),
    ):
        with pytest.raises(LLMAuthenticationError):
            await provider.generate([{"role": "user", "content": "hi"}])

    # Rate limit error
    with patch(
        "litellm.acompletion",
        side_effect=RateLimitError("rate limited", "openai", "gpt"),
    ):
        with pytest.raises(LLMRateLimitError):
            await provider.generate([{"role": "user", "content": "hi"}])

    # Timeout error
    with patch("litellm.acompletion", side_effect=Timeout("timeout error", "gpt", "openai")):
        with pytest.raises(LLMTimeoutError):
            await provider.generate([{"role": "user", "content": "hi"}])

    # Generic error
    with patch("litellm.acompletion", side_effect=Exception("api failure")):
        with pytest.raises(LLMError) as exc_info:
            await provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == "api_error"


# Additional factory tests for LLM
def test_llm_factory():
    """Verify that get_llm_provider selects litellm and fails on unknown."""
    with patch.dict(os.environ, {"LLM_PROVIDER": "litellm"}):
        provider = get_llm_provider()
        assert isinstance(provider, LiteLlmProvider)

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("unknown_llm_foo")


# Service and OpenAI provider basic unit tests
@pytest.mark.asyncio
async def test_service_bge_m3_provider():
    """Verify that ServiceBgeM3Provider forwards call to BGEM3Client."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.vectors = [[0.9, 0.8]]
    mock_client.encode_dense = AsyncMock(return_value=mock_result)

    provider = ServiceBgeM3Provider(client=mock_client)
    res = await provider.embed_texts(["test"])
    assert res == [[0.9, 0.8]]
    mock_client.encode_dense.assert_awaited_once_with(["test"])


@pytest.mark.asyncio
async def test_openai_embedding_provider():
    """Verify that OpenAIEmbeddingProvider forwards call to OpenAI client."""
    mock_response = MagicMock()
    mock_data = MagicMock()
    mock_data.embedding = [0.5, 0.6]
    mock_response.data = [mock_data]

    mock_embeddings_client = MagicMock()
    mock_embeddings_client.create = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.embeddings = mock_embeddings_client

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        provider = OpenAIEmbeddingProvider()
        res = await provider.embed_texts(["hello"])
        assert res == [[0.5, 0.6]]
        mock_embeddings_client.create.assert_awaited_once_with(
            input=["hello"], model="text-embedding-3-small"
        )
