"""Tests for Docling-serve HTTP client helpers."""

import pytest


pytestmark = pytest.mark.requires_extras


@pytest.mark.parametrize(
    "profile,expected_table_mode",
    [
        ("speed", "fast"),
        ("quality", "accurate"),
        ("scan", "accurate"),
    ],
)
def test_profile_uses_docling_parse_backend(profile: str, expected_table_mode: str) -> None:
    """Each profile must use canonical docling_parse backend and correct table_mode."""
    from src.ingestion.docling_client import DoclingConfig

    cfg = DoclingConfig(profile=profile)
    assert cfg.pdf_backend == "docling_parse", (
        f"Profile {profile!r}: expected pdf_backend='docling_parse', got {cfg.pdf_backend!r}"
    )
    assert cfg.table_mode == expected_table_mode, (
        f"Profile {profile!r}: expected table_mode={expected_table_mode!r}, got {cfg.table_mode!r}"
    )


def test_build_chunking_form_data_omits_invalid_tokenizer_word():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig(tokenizer="word"))
    data = client._build_chunking_form_data()

    assert "chunking_tokenizer" not in data


def test_build_chunking_form_data_omits_invalid_tokenizer_huggingface():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig(tokenizer="huggingface"))
    data = client._build_chunking_form_data()

    assert "chunking_tokenizer" not in data


def test_build_chunking_form_data_includes_hf_model_id():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig(tokenizer="sentence-transformers/all-MiniLM-L6-v2"))
    data = client._build_chunking_form_data()

    assert data["chunking_tokenizer"] == "sentence-transformers/all-MiniLM-L6-v2"


def test_parse_page_range_prefers_page_numbers():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig())
    raw_chunk = {"page_numbers": [3, 4, 5], "metadata": {"origin": {"filename": "x.pdf"}}}

    assert client._parse_page_range_from_chunk(raw_chunk) == (3, 5)


def test_parse_page_range_falls_back_to_meta():
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    client = DoclingClient(DoclingConfig())
    raw_chunk = {"meta": {"page": 7}}

    assert client._parse_page_range_from_chunk(raw_chunk) == (7, 7)


class TestDoclingClientSync:
    """Tests for sync methods."""

    def test_chunk_file_sync_exists(self):
        """chunk_file_sync() method should exist."""
        from src.ingestion.docling_client import DoclingClient

        assert hasattr(DoclingClient, "chunk_file_sync")

    def test_chunk_file_sync_is_not_coroutine(self):
        """chunk_file_sync() should be sync."""
        import asyncio

        from src.ingestion.docling_client import DoclingClient

        assert not asyncio.iscoroutinefunction(DoclingClient.chunk_file_sync)


# ---------------------------------------------------------------------------
# D2 — HTTP DoclingClient.chunk_file_sync (mock httpx.Client.post)
# ---------------------------------------------------------------------------


class TestDoclingClientSyncHTTP:
    """HTTP-mocked tests for chunk_file_sync."""

    def _make_client(self, **config_kwargs):
        from src.ingestion.docling_client import DoclingClient, DoclingConfig

        return DoclingClient(DoclingConfig(**config_kwargs))

    def test_empty_chunks_response_logs_warning_and_returns_empty(self, tmp_path, caplog) -> None:
        """{'chunks': []} from server → logs a warning and returns empty list."""
        import logging
        from unittest.mock import MagicMock, patch

        doc = tmp_path / "test.md"
        doc.write_text("# hello", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chunks": []}
        mock_response.raise_for_status = MagicMock()

        client = self._make_client()
        with patch("httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = lambda *_: mock_http
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_response

            with caplog.at_level(logging.WARNING, logger="src.ingestion.docling_client"):
                result = client.chunk_file_sync(doc)

        assert result == []
        assert any(
            "0 chunks" in r.message or "chunks" in r.message.lower() for r in caplog.records
        ), "Expected a warning log about 0 chunks"

    def test_contextualize_true_uses_contextualized_text(self, tmp_path) -> None:
        """contextualize=True must prefer contextualized_text field over text."""
        from unittest.mock import MagicMock, patch

        doc = tmp_path / "test.md"
        doc.write_text("# content", encoding="utf-8")

        raw_chunk = {
            "text": "raw text",
            "contextualized_text": "Intro\nraw text",
            "seq_no": 0,
            "headings": [],
            "page_numbers": [],
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chunks": [raw_chunk]}
        mock_response.raise_for_status = MagicMock()

        client = self._make_client()
        with patch("httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = lambda *_: mock_http
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_response

            chunks = client.chunk_file_sync(doc, contextualize=True)

        assert len(chunks) == 1
        assert chunks[0].text == "Intro\nraw text"

    def test_contextualize_false_uses_text_field(self, tmp_path) -> None:
        """contextualize=False must use the plain text field."""
        from unittest.mock import MagicMock, patch

        doc = tmp_path / "test.md"
        doc.write_text("# content", encoding="utf-8")

        raw_chunk = {
            "text": "raw text",
            "contextualized_text": "Intro\nraw text",
            "seq_no": 0,
            "headings": [],
            "page_numbers": [],
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chunks": [raw_chunk]}
        mock_response.raise_for_status = MagicMock()

        client = self._make_client()
        with patch("httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = lambda *_: mock_http
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = mock_response

            chunks = client.chunk_file_sync(doc, contextualize=False)

        assert len(chunks) == 1
        assert chunks[0].text == "raw text"

    def test_file_too_large_raises_before_http(self, tmp_path) -> None:
        """FileTooLargeError must be raised in the preflight check WITHOUT calling HTTP."""
        from unittest.mock import MagicMock, patch

        from src.ingestion.docling_client import FileTooLargeError

        doc = tmp_path / "big.pdf"
        doc.write_bytes(b"x" * 100)  # 100 bytes

        client = self._make_client(max_file_size_bytes=10)  # limit 10 bytes

        with patch("httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = lambda *_: mock_http
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(FileTooLargeError):
                client.chunk_file_sync(doc)

            # HTTP must not have been called
            mock_http.post.assert_not_called()
