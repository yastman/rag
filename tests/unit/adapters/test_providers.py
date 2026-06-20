"""Unit tests for embedding and LLM provider adapters."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import AuthenticationError, RateLimitError, Timeout

from src.adapters.embeddings import (
    BgeM3EmbeddingProvider,
    LocalBgeM3Provider,
    OpenAIEmbeddingProvider,
)
from src.adapters.llm import (
    LiteLlmProvider,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)


# 1 no FlagEmbedding import at module import
def test_no_flagembedding_import_at_module_import():
    """Verify that LocalBgeM3Provider can be constructed without importing FlagEmbedding."""
    with patch.dict(sys.modules, {"FlagEmbedding": None}):
        provider = LocalBgeM3Provider()
        assert provider.model_name == "BAAI/bge-m3"


# 2 no model load on __init__
def test_no_model_load_on_init():
    """Verify that BGEM3FlagModel is not instantiated during provider construction."""
    with patch("FlagEmbedding.BGEM3FlagModel") as mock_model_cls:
        _ = LocalBgeM3Provider()
        mock_model_cls.assert_not_called()


# 3 empty embed_texts([]) -> [] no load
@pytest.mark.asyncio
async def test_empty_embed_texts_no_load():
    """Verify that passing an empty list to embed_texts returns empty list without loading model."""
    with patch("FlagEmbedding.BGEM3FlagModel") as mock_model_cls:
        provider = LocalBgeM3Provider()
        result = await provider.embed_texts([])
        assert result == []
        mock_model_cls.assert_not_called()


# 4 first embed_texts() loads lazily and 5 second call reuses model
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


# 6 LiteLlmProvider calls the canonical LiteLLM router client
@pytest.mark.asyncio
async def test_litellm_provider_calls_router_client():
    """Verify that LiteLlmProvider.generate uses the shared LiteLLM router path."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "LiteLLM response content"
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch(
        "src.runtime.llm.create_litellm_chat_client", return_value=mock_client
    ) as mock_create_client:
        provider = LiteLlmProvider(default_model="gpt-4o-mini")
        res = await provider.generate([{"role": "user", "content": "hello"}])
        assert res == "LiteLLM response content"
        mock_create_client.assert_called_once_with(model="gpt-4o-mini", timeout=60.0)
        mock_client.chat.completions.create.assert_awaited_once_with(
            messages=[{"role": "user", "content": "hello"}]
        )


# 7 LiteLLM errors normalized
@pytest.mark.asyncio
async def test_litellm_errors_normalized():
    """Verify that LiteLLM errors are normalized to the unified exception classes."""
    provider = LiteLlmProvider()

    def _client_with_error(exc: Exception) -> MagicMock:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=exc)
        return mock_client

    # Auth error
    with patch(
        "src.runtime.llm.create_litellm_chat_client",
        return_value=_client_with_error(AuthenticationError("auth failed", "openai", "gpt")),
    ):
        with pytest.raises(LLMAuthenticationError):
            await provider.generate([{"role": "user", "content": "hi"}])

    # Rate limit error
    with patch(
        "src.runtime.llm.create_litellm_chat_client",
        return_value=_client_with_error(RateLimitError("rate limited", "openai", "gpt")),
    ):
        with pytest.raises(LLMRateLimitError):
            await provider.generate([{"role": "user", "content": "hi"}])

    # Timeout error
    with patch(
        "src.runtime.llm.create_litellm_chat_client",
        return_value=_client_with_error(Timeout("timeout error", "gpt", "openai")),
    ):
        with pytest.raises(LLMTimeoutError):
            await provider.generate([{"role": "user", "content": "hi"}])

    # Generic error
    with patch(
        "src.runtime.llm.create_litellm_chat_client",
        return_value=_client_with_error(Exception("api failure")),
    ):
        with pytest.raises(LLMError) as exc_info:
            await provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == "api_error"


# Service and OpenAI provider basic unit tests
@pytest.mark.asyncio
async def test_service_bge_m3_provider():
    """Verify that BgeM3EmbeddingProvider forwards call to BGEM3Client (service_bge_m3 factory name)."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.vectors = [[0.9, 0.8]]
    mock_client.encode_dense = AsyncMock(return_value=mock_result)

    provider = BgeM3EmbeddingProvider(client=mock_client)
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
