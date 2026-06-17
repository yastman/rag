"""Tests for DoclingClient streaming / bounded-memory behavior (#2622).

These tests prove that chunk_file() and chunk_file_sync() no longer
read entire files into memory, and that oversized files are rejected
with a controlled error before any upload attempt.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.requires_extras


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_docling_response(n_chunks: int = 1) -> dict:
    return {
        "chunks": [
            {"text": f"chunk {i}", "seq_no": i, "page_numbers": [1]} for i in range(n_chunks)
        ]
    }


# ---------------------------------------------------------------------------
# Max file size preflight — async
# ---------------------------------------------------------------------------


class TestMaxFileSizePreflight:
    """Oversized files must be rejected before any HTTP call is made."""

    @pytest.mark.asyncio
    async def test_chunk_file_raises_when_file_exceeds_max_size(self, tmp_path: Path):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig, FileTooLargeError

        big_file = tmp_path / "big.pdf"
        big_file.write_bytes(b"x" * 100)

        config = DoclingConfig(max_file_size_bytes=50)
        async with DoclingClient(config) as client:
            with pytest.raises(FileTooLargeError):
                await client.chunk_file(big_file)

    @pytest.mark.asyncio
    async def test_chunk_file_does_not_call_http_when_oversized(self, tmp_path: Path):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig, FileTooLargeError

        big_file = tmp_path / "big.pdf"
        big_file.write_bytes(b"x" * 100)

        config = DoclingConfig(max_file_size_bytes=50)
        async with DoclingClient(config) as client:
            with patch.object(client, "_client") as mock_http:
                with pytest.raises(FileTooLargeError):
                    await client.chunk_file(big_file)
                mock_http.post.assert_not_called()

    def test_chunk_file_sync_raises_when_file_exceeds_max_size(self, tmp_path: Path):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig, FileTooLargeError

        big_file = tmp_path / "big.pdf"
        big_file.write_bytes(b"x" * 100)

        config = DoclingConfig(max_file_size_bytes=50)
        client = DoclingClient(config)
        with pytest.raises(FileTooLargeError):
            client.chunk_file_sync(big_file)


# ---------------------------------------------------------------------------
# No full-file read — async
# ---------------------------------------------------------------------------


class TestNoFullFileRead:
    """chunk_file() must NOT call read_bytes() / read() on the whole file."""

    @pytest.mark.asyncio
    async def test_chunk_file_does_not_call_read_bytes(self, tmp_path: Path):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF small content")

        config = DoclingConfig()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_docling_response()

        async with DoclingClient(config) as client:
            with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                # Patch anyio.Path.read_bytes to detect if it's called
                with patch("anyio.Path.read_bytes", new_callable=AsyncMock) as mock_rb:
                    await client.chunk_file(pdf)
                    mock_rb.assert_not_called()

    @pytest.mark.asyncio
    async def test_chunk_file_passes_file_handle_not_bytes(self, tmp_path: Path):
        """The files dict passed to httpx must use a file-like object, not raw bytes."""
        from src.ingestion.docling_client import DoclingClient, DoclingConfig

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF small content")

        config = DoclingConfig()
        captured: list = []

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_docling_response()

        async def fake_post(url, *, files, data):
            captured.append(files)
            return mock_response

        async with DoclingClient(config) as client:
            with patch.object(client._client, "post", side_effect=fake_post):
                await client.chunk_file(pdf)

        assert captured, "post was not called"
        files_arg = captured[0]
        # The value tuple is (filename, file_content, mime_type)
        _filename, file_content, _mime = files_arg["files"]
        # Must be a file-like object (has read), not plain bytes
        assert hasattr(file_content, "read"), (
            f"Expected file-like object with .read(), got {type(file_content)}"
        )


# ---------------------------------------------------------------------------
# No full-file read — sync
# ---------------------------------------------------------------------------


class TestNoFullFileReadSync:
    """chunk_file_sync() must NOT call Path.read_bytes()."""

    def test_chunk_file_sync_does_not_call_read_bytes(self, tmp_path: Path):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF small content")

        config = DoclingConfig()
        captured: list = []

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_docling_response()

        def fake_post(url, *, files, data):
            captured.append(files)
            return mock_response

        client = DoclingClient(config)
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.post.side_effect = fake_post
            mock_client_cls.return_value = mock_http

            with patch.object(Path, "read_bytes") as mock_rb:
                client.chunk_file_sync(pdf)
                mock_rb.assert_not_called()

    def test_chunk_file_sync_passes_file_handle_not_bytes(self, tmp_path: Path):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF small content")

        config = DoclingConfig()
        captured: list = []

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_docling_response()

        def fake_post(url, *, files, data):
            captured.append(files)
            return mock_response

        client = DoclingClient(config)
        with patch("httpx.Client") as mock_client_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.post.side_effect = fake_post
            mock_client_cls.return_value = mock_http

            client.chunk_file_sync(pdf)

        assert captured, "post was not called"
        files_arg = captured[0]
        _filename, file_content, _mime = files_arg["files"]
        assert hasattr(file_content, "read"), (
            f"Expected file-like object with .read(), got {type(file_content)}"
        )
