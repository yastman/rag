"""Unit tests for src/ingestion/document_parser.py."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("pymupdf", reason="pymupdf not installed (ingest extra)")
pytest.importorskip("docling", reason="docling not installed (ingest extra)")
pytestmark = pytest.mark.requires_extras

import src.ingestion.document_parser as document_parser
from src.ingestion.document_parser import (
    ParsedDocument,
    ParserCache,
    UniversalDocumentParser,
    parse_document,
)


class TestParsedDocument:
    """Test ParsedDocument dataclass."""

    def test_parsed_document_creation(self):
        """Test basic ParsedDocument creation."""
        doc = ParsedDocument(
            filename="test.pdf",
            title="Test Document",
            content="Document content",
        )

        assert doc.filename == "test.pdf"
        assert doc.title == "Test Document"
        assert doc.content == "Document content"
        assert doc.num_pages is None
        assert doc.metadata == {}

    def test_parsed_document_with_metadata(self):
        """Test ParsedDocument with all fields."""
        doc = ParsedDocument(
            filename="test.pdf",
            title="Test",
            content="Content",
            num_pages=10,
            metadata={"author": "John"},
        )

        assert doc.num_pages == 10
        assert doc.metadata["author"] == "John"

    def test_parsed_document_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        doc = ParsedDocument(
            filename="test.pdf",
            title="Test",
            content="Content",
        )

        assert doc.metadata == {}
        assert isinstance(doc.metadata, dict)


class TestParserCache:
    """Test ParserCache class."""

    def test_cache_init_creates_directory(self):
        """Test that cache creates directory on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "test_cache"
            _cache = ParserCache(cache_dir=cache_dir)

            assert cache_dir.exists()

    def test_cache_get_miss(self):
        """Test cache miss returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ParserCache(cache_dir=Path(tmpdir))

            # Create a test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("content")

            result = cache.get(test_file)

            assert result is None

    def test_cache_set_and_get(self):
        """Test setting and getting cached content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ParserCache(cache_dir=Path(tmpdir))

            # Create a test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("original content")

            # Cache some content
            cache.set(test_file, "cached content")

            # Get cached content
            result = cache.get(test_file)

            assert result == "cached content"

    def test_cache_hash_based(self):
        """Test that cache is based on file content hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ParserCache(cache_dir=Path(tmpdir))

            # Create two files with same content
            file1 = Path(tmpdir) / "file1.txt"
            file2 = Path(tmpdir) / "file2.txt"
            file1.write_text("same content")
            file2.write_text("same content")

            # Cache file1
            cache.set(file1, "cached")

            # file2 should hit cache (same content hash)
            result = cache.get(file2)
            assert result == "cached"


class TestUniversalDocumentParser:
    """Test UniversalDocumentParser class."""

    def test_parser_init_with_cache(self):
        """Test parser init with cache enabled."""
        parser = UniversalDocumentParser(use_cache=True)

        assert parser.use_cache is True
        assert parser.cache is not None

    def test_parser_init_without_cache(self):
        """Test parser init with cache disabled."""
        parser = UniversalDocumentParser(use_cache=False)

        assert parser.use_cache is False
        assert parser.cache is None

    def test_parser_formats(self):
        """Test supported format constants."""
        assert ".pdf" in UniversalDocumentParser.PDF_FORMATS
        assert ".docx" in UniversalDocumentParser.DOCLING_FORMATS
        assert ".csv" in UniversalDocumentParser.DOCLING_FORMATS
        assert ".xlsx" in UniversalDocumentParser.DOCLING_FORMATS

    def test_parser_file_not_found(self):
        """Test FileNotFoundError for missing file."""
        parser = UniversalDocumentParser(use_cache=False)

        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/file.pdf")

    def test_parser_unsupported_format(self):
        """Test ValueError for unsupported format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with unsupported extension
            test_file = Path(tmpdir) / "test.xyz"
            test_file.write_text("content")

            parser = UniversalDocumentParser(use_cache=False)

            with pytest.raises(ValueError, match="Unsupported format"):
                parser.parse_file(test_file)

    def test_parser_docling_lazy_init(self):
        """Test that Docling converter is lazily initialized."""
        parser = UniversalDocumentParser(use_cache=False)

        assert parser.docling_converter is None

    @patch.object(document_parser, "DocumentConverter")
    def test_parser_docling_converter_created(self, mock_converter_cls):
        """Test that Docling converter is created on first use."""
        mock_converter = MagicMock()
        mock_converter_cls.return_value = mock_converter

        parser = UniversalDocumentParser(use_cache=False)
        converter = parser._get_docling_converter()

        assert converter is mock_converter
        mock_converter_cls.assert_called_once()

    @patch.object(document_parser, "DocumentConverter")
    def test_parser_docling_converter_reused(self, mock_converter_cls):
        """Test that Docling converter is reused."""
        mock_converter = MagicMock()
        mock_converter_cls.return_value = mock_converter

        parser = UniversalDocumentParser(use_cache=False)

        # Get converter twice
        converter1 = parser._get_docling_converter()
        converter2 = parser._get_docling_converter()

        assert converter1 is converter2
        mock_converter_cls.assert_called_once()  # Only created once


class TestParsePDF:
    """Test PDF parsing."""

    @patch.object(document_parser, "pymupdf")
    def test_parse_pdf_success(self, mock_pymupdf):
        """Test successful PDF parsing."""
        # Create mock PDF document
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page content"

        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.metadata = {"title": "Test PDF", "author": "Author"}

        mock_pymupdf.open.return_value = mock_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy PDF file
            pdf_file = Path(tmpdir) / "test.pdf"
            pdf_file.write_bytes(b"%PDF-1.4")

            parser = UniversalDocumentParser(use_cache=False)
            result = parser._parse_pdf(pdf_file)

            assert result.filename == "test.pdf"
            assert result.title == "Test PDF"
            assert result.content == "Page content"
            assert result.num_pages == 1
            assert result.metadata["parser"] == "pymupdf"

    @patch.object(document_parser, "pymupdf")
    def test_parse_pdf_no_metadata(self, mock_pymupdf):
        """Test PDF parsing when metadata is None."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.metadata = None

        mock_pymupdf.open.return_value = mock_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_file = Path(tmpdir) / "test.pdf"
            pdf_file.write_bytes(b"%PDF-1.4")

            parser = UniversalDocumentParser(use_cache=False)
            result = parser._parse_pdf(pdf_file)

            # Should use stem as title when no metadata
            assert result.title == "test"


class TestParseWithDocling:
    """Test Docling parsing."""

    @patch.object(document_parser, "DocumentConverter")
    def test_parse_docling_success(self, mock_converter_cls):
        """Test successful Docling parsing."""
        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "# Document\n\nContent"

        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result
        mock_converter_cls.return_value = mock_converter

        with tempfile.TemporaryDirectory() as tmpdir:
            docx_file = Path(tmpdir) / "test.docx"
            docx_file.write_bytes(b"dummy")

            parser = UniversalDocumentParser(use_cache=False)
            result = parser._parse_with_docling(docx_file)

            assert result.filename == "test.docx"
            assert result.title == "test"
            assert result.content == "# Document\n\nContent"
            assert result.metadata["parser"] == "docling"
            assert result.metadata["format"] == "docx"


class TestParseFile:
    """Test main parse_file method."""

    @patch.object(document_parser, "pymupdf")
    def test_parse_file_uses_cache(self, mock_pymupdf):
        """Test that parse_file uses cache."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.metadata = {}

        mock_pymupdf.open.return_value = mock_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_file = Path(tmpdir) / "test.pdf"
            pdf_file.write_bytes(b"%PDF-1.4")

            parser = UniversalDocumentParser(use_cache=True)
            parser.cache = ParserCache(cache_dir=Path(tmpdir) / "cache")

            # First call - should parse
            _result1 = parser.parse_file(pdf_file)

            # Reset mock to verify second call uses cache
            mock_pymupdf.open.reset_mock()

            # Second call - should use cache
            result2 = parser.parse_file(pdf_file)

            # Verify second call didn't parse
            mock_pymupdf.open.assert_not_called()
            assert result2.metadata["source"] == "cache"


class TestConvenienceFunction:
    """Test parse_document convenience function."""

    @patch.object(document_parser, "pymupdf")
    def test_parse_document_function(self, mock_pymupdf):
        """Test parse_document convenience function."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.metadata = {}

        mock_pymupdf.open.return_value = mock_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_file = Path(tmpdir) / "test.pdf"
            pdf_file.write_bytes(b"%PDF-1.4")

            result = parse_document(pdf_file, use_cache=False)

            assert isinstance(result, ParsedDocument)
            assert result.content == "Content"
