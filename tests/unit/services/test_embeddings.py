"""Unit tests for EmbeddingService."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.services.embeddings import EmbeddingService


# =============================================================================
# TestEmbeddingServiceInit
# =============================================================================


class TestEmbeddingServiceInit:
    """Tests for EmbeddingService initialization."""

    def test_init_stores_base_url(self):
        """Test that base_url is stored correctly."""
        with patch("httpx.AsyncClient"):
            service = EmbeddingService("http://localhost:8001")
            assert service.base_url == "http://localhost:8001"

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base_url."""
        with patch("httpx.AsyncClient"):
            service = EmbeddingService("http://localhost:8001/")
            assert service.base_url == "http://localhost:8001"

    def test_init_strips_multiple_trailing_slashes(self):
        """Test that multiple trailing slashes are stripped."""
        with patch("httpx.AsyncClient"):
            service = EmbeddingService("http://localhost:8001///")
            # rstrip("/") removes all trailing slashes
            assert service.base_url == "http://localhost:8001"

    def test_init_creates_httpx_client(self):
        """Test that httpx.AsyncClient is created on init."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            service = EmbeddingService("http://localhost:8001")

            mock_client_class.assert_called_once_with(timeout=30.0)
            assert service.client == mock_client

    def test_init_with_different_urls(self):
        """Test initialization with various URL formats."""
        test_urls = [
            ("http://localhost:8001", "http://localhost:8001"),
            ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
            ("https://api.example.com/v1/", "https://api.example.com/v1"),
            ("http://bge-m3:8001", "http://bge-m3:8001"),
        ]

        with patch("httpx.AsyncClient"):
            for input_url, expected_url in test_urls:
                service = EmbeddingService(input_url)
                assert service.base_url == expected_url, f"Failed for input: {input_url}"


# =============================================================================
# TestEmbeddingServiceEmbedQuery
# =============================================================================


class TestEmbeddingServiceEmbedQuery:
    """Tests for EmbeddingService.embed_query method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock httpx.AsyncClient."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def service_with_mock_client(self, mock_client):
        """Create EmbeddingService with mocked client."""
        with patch("httpx.AsyncClient", return_value=mock_client):
            return EmbeddingService("http://localhost:8001")

    async def test_embed_query_returns_vector(self, service_with_mock_client, mock_client):
        """Test that embed_query returns the embedding vector."""
        expected_vector = [0.1, 0.2, 0.3, 0.4, 0.5]

        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [expected_vector]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await service_with_mock_client.embed_query("test query")

        assert result == expected_vector

    async def test_embed_query_calls_correct_endpoint(self, service_with_mock_client, mock_client):
        """Test that embed_query calls the /encode/dense endpoint."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1, 0.2]]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service_with_mock_client.embed_query("test query")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8001/encode/dense"

    async def test_embed_query_sends_text_as_array(self, service_with_mock_client, mock_client):
        """Test that embed_query sends text wrapped in array."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1, 0.2]]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        test_text = "my test query"
        await service_with_mock_client.embed_query(test_text)

        call_args = mock_client.post.call_args
        assert call_args[1]["json"] == {"texts": [test_text]}

    async def test_embed_query_raises_on_http_error(self, service_with_mock_client, mock_client):
        """Test that embed_query raises HTTPStatusError on HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client.post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await service_with_mock_client.embed_query("test query")

    async def test_embed_query_raises_on_404_error(self, service_with_mock_client, mock_client):
        """Test that embed_query raises HTTPStatusError on 404."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client.post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await service_with_mock_client.embed_query("test query")

    async def test_embed_query_returns_first_embedding_only(
        self, service_with_mock_client, mock_client
    ):
        """Test that only the first embedding is returned (index 0)."""
        # API returns multiple embeddings but we only sent one text
        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await service_with_mock_client.embed_query("test query")

        assert result == [0.1, 0.2]

    async def test_embed_query_handles_1024_dim_vector(self, service_with_mock_client, mock_client):
        """Test handling of BGE-M3's 1024-dimensional vectors."""
        expected_vector = [0.001 * i for i in range(1024)]

        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [expected_vector]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await service_with_mock_client.embed_query("test query")

        assert len(result) == 1024
        assert result == expected_vector

    async def test_embed_query_with_empty_text(self, service_with_mock_client, mock_client):
        """Test embed_query with empty string."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.0, 0.0]]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service_with_mock_client.embed_query("")

        # Should still make the request
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[1]["json"] == {"texts": [""]}

    async def test_embed_query_with_unicode_text(self, service_with_mock_client, mock_client):
        """Test embed_query with unicode/cyrillic text."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.5, 0.5]]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        cyrillic_text = "Кримінальний кодекс України"
        await service_with_mock_client.embed_query(cyrillic_text)

        call_args = mock_client.post.call_args
        assert call_args[1]["json"] == {"texts": [cyrillic_text]}


# =============================================================================
# TestEmbeddingServiceClose
# =============================================================================


class TestEmbeddingServiceClose:
    """Tests for EmbeddingService.close method."""

    async def test_close_calls_aclose_on_client(self):
        """Test that close() calls aclose() on the HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService("http://localhost:8001")

        await service.close()

        mock_client.aclose.assert_called_once()

    async def test_close_can_be_called_multiple_times(self):
        """Test that close() can be called multiple times without error."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService("http://localhost:8001")

        # Call close multiple times
        await service.close()
        await service.close()

        # aclose should be called twice
        assert mock_client.aclose.call_count == 2


# =============================================================================
# Integration-style tests (still mocked, but testing flow)
# =============================================================================


class TestEmbeddingServiceFlow:
    """Test typical usage flow of EmbeddingService."""

    async def test_full_lifecycle(self):
        """Test create -> use -> close lifecycle."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1, 0.2, 0.3]]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            # Create
            service = EmbeddingService("http://localhost:8001/")
            assert service.base_url == "http://localhost:8001"

            # Use
            result = await service.embed_query("test")
            assert result == [0.1, 0.2, 0.3]

            # Close
            await service.close()
            mock_client.aclose.assert_called_once()

    async def test_multiple_queries(self):
        """Test making multiple queries with the same service."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        # Different responses for different queries
        responses = [
            {"dense_vecs": [[0.1, 0.2]]},
            {"dense_vecs": [[0.3, 0.4]]},
            {"dense_vecs": [[0.5, 0.6]]},
        ]

        mock_responses = []
        for resp_data in responses:
            mock_resp = MagicMock()
            mock_resp.json.return_value = resp_data
            mock_resp.raise_for_status = MagicMock()
            mock_responses.append(mock_resp)

        mock_client.post.side_effect = mock_responses

        with patch("httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService("http://localhost:8001")

            result1 = await service.embed_query("query1")
            result2 = await service.embed_query("query2")
            result3 = await service.embed_query("query3")

            assert result1 == [0.1, 0.2]
            assert result2 == [0.3, 0.4]
            assert result3 == [0.5, 0.6]
            assert mock_client.post.call_count == 3
