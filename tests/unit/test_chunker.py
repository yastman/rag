"""Unit tests for src/ingestion/chunker.py."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ingestion.chunker import (
    Chunk,
    ChunkingStrategy,
    DocumentChunker,
    _chunk_csv_legacy,
    _parse_csv_row_metadata,
    chunk_csv_by_rows,
)


class TestChunk:
    """Test Chunk dataclass."""

    def test_chunk_creation(self):
        """Test basic Chunk creation."""
        chunk = Chunk(
            text="Test text",
            chunk_id=0,
            document_name="test.pdf",
            article_number="115",
        )

        assert chunk.text == "Test text"
        assert chunk.chunk_id == 0
        assert chunk.document_name == "test.pdf"
        assert chunk.article_number == "115"
        assert chunk.chapter is None
        assert chunk.section is None
        assert chunk.order == 0

    def test_chunk_with_metadata(self):
        """Test Chunk with extra metadata."""
        chunk = Chunk(
            text="Test text",
            chunk_id=1,
            document_name="test.pdf",
            article_number="116",
            chapter="Глава I",
            section="Розділ I",
            page_range=(1, 5),
            order=1,
            extra_metadata={"price": 50000, "city": "Varna"},
        )

        assert chunk.chapter == "Глава I"
        assert chunk.section == "Розділ I"
        assert chunk.page_range == (1, 5)
        assert chunk.extra_metadata["price"] == 50000


class TestChunkingStrategy:
    """Test ChunkingStrategy enum."""

    def test_strategy_values(self):
        """Test enum values."""
        assert ChunkingStrategy.SEMANTIC.value == "semantic"


class TestDocumentChunkerSemantic:
    """Test semantic chunking strategy."""

    def test_semantic_preserves_sections(self):
        """Test that semantic chunking preserves section boundaries."""
        chunker = DocumentChunker(
            chunk_size=500,
            overlap=50,
            strategy=ChunkingStrategy.SEMANTIC,
        )

        text = """
        Розділ I. ЗАГАЛЬНІ ПОЛОЖЕННЯ

        Стаття 1. Завдання Кримінального кодексу України
        Кримінальний кодекс України має своїм завданням правове забезпечення
        охорони прав і свобод людини і громадянина.

        Стаття 2. Підстава кримінальної відповідальності
        Підставою кримінальної відповідальності є вчинення особою суспільно
        небезпечного діяння.
        """

        chunks = chunker.chunk_text(text, "criminal_code.pdf", "1")

        assert len(chunks) >= 1
        # Check that chunks preserve structure
        assert any("Стаття" in c.text for c in chunks)

    def test_semantic_chapters(self):
        """Test semantic chunking with Глава markers."""
        chunker = DocumentChunker(
            chunk_size=200,
            overlap=20,
            strategy=ChunkingStrategy.SEMANTIC,
        )

        text = """Глава 1 Загальні положення
        Текст першої глави.

        Глава 2 Особлива частина
        Текст другої глави."""

        chunks = chunker.chunk_text(text, "test.pdf", "1")

        assert len(chunks) >= 1

    def test_semantic_article_numbers(self):
        """Test semantic chunking extracts article markers."""
        chunker = DocumentChunker(
            chunk_size=100,
            overlap=10,
            strategy=ChunkingStrategy.SEMANTIC,
        )

        text = "Стаття 115. Умисне вбивство. Текст статті про вбивство."

        chunks = chunker.chunk_text(text, "test.pdf", "115")

        assert len(chunks) >= 1
        assert "115" in chunks[0].text


class TestExtractMetadata:
    """Test metadata extraction from chunk text."""

    def test_extract_article_number(self):
        """Test article number extraction."""
        text = "Стаття 115. Умисне вбивство"
        metadata = DocumentChunker.extract_metadata(text)

        assert metadata.get("article_number") == "115"

    def test_extract_article_number_short_form(self):
        """Test article number extraction with Ст. format."""
        text = "Ст. 256 визначає..."
        metadata = DocumentChunker.extract_metadata(text)

        assert metadata.get("article_number") == "256"

    def test_extract_chapter_roman(self):
        """Test chapter extraction with Roman numerals."""
        text = "Розділ III. ЗЛОЧИНИ"
        metadata = DocumentChunker.extract_metadata(text)

        assert metadata.get("chapter") == "III"

    def test_extract_chapter_arabic(self):
        """Test chapter extraction with Arabic numerals."""
        text = "Глава 5 Майнові злочини"
        metadata = DocumentChunker.extract_metadata(text)

        assert metadata.get("chapter") == "5"

    def test_extract_no_metadata(self):
        """Test extraction when no metadata present."""
        text = "Просто текст без маркерів"
        metadata = DocumentChunker.extract_metadata(text)

        assert metadata == {}


class TestChunkCSVByRows:
    """Test CSV row-based chunking (uses Docling when available)."""

    def test_csv_chunking_basic(self):
        """Test basic CSV chunking returns chunks with content from all rows."""
        csv_content = """Название,Город,Цена (€),Комнат
Квартира 1,Варна,50000,2
Квартира 2,Бургас,75000,3
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()

            chunks = chunk_csv_by_rows(Path(f.name), "properties.csv")

        assert len(chunks) >= 1
        # All row data should appear somewhere in the chunks
        all_text = " ".join(c.text for c in chunks)
        assert "Варна" in all_text
        assert "Бургас" in all_text

    def test_csv_chunking_metadata(self):
        """Test that CSV chunking produces chunks with metadata."""
        csv_content = """Название,Город,Цена (€),Комнат,Площадь (м²)
Апартамент,Несебър,120000,3,85
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()

            chunks = chunk_csv_by_rows(Path(f.name), "test.csv")

        assert len(chunks) >= 1
        assert chunks[0].extra_metadata is not None
        # Docling path uses unified metadata schema
        assert chunks[0].extra_metadata.get("source_type") == "csv"
        assert chunks[0].document_name == "test.csv"
        # Row content should be in the chunk text
        assert "Несебър" in chunks[0].text

    def test_csv_chunking_chunk_id(self):
        """Test that chunk IDs are sequential."""
        csv_content = """Название,Город
Row1,City1
Row2,City2
Row3,City3
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()

            chunks = chunk_csv_by_rows(Path(f.name), "test.csv")

        # Chunk IDs should be sequential regardless of count
        assert chunks[0].chunk_id == 0
        for i, c in enumerate(chunks):
            assert c.chunk_id == i
            assert c.order == i


class TestParseCSVRowMetadata:
    """Test CSV row metadata parsing."""

    def test_parse_numeric_fields(self):
        """Test numeric field parsing."""
        row = {
            "Цена (€)": "150000",
            "Комнат": "3",
            "Площадь (м²)": "95.5",
            "Этаж": "5",
        }

        metadata = _parse_csv_row_metadata(row)

        assert metadata["price"] == 150000
        assert metadata["rooms"] == 3
        assert metadata["area"] == 95.5
        assert metadata["floor"] == 5

    def test_parse_number_with_spaces(self):
        """Test parsing numbers with space formatting."""
        row = {"Цена (€)": "120 000"}

        metadata = _parse_csv_row_metadata(row)

        assert metadata["price"] == 120000

    def test_parse_boolean_fields(self):
        """Test boolean field parsing."""
        row_yes = {"Мебель": "есть", "Круглогодичность": "да"}
        row_no = {"Мебель": "нет", "Круглогодичность": ""}

        metadata_yes = _parse_csv_row_metadata(row_yes)
        metadata_no = _parse_csv_row_metadata(row_no)

        assert metadata_yes["furnished"] is True
        assert metadata_yes["year_round"] is True
        assert metadata_no.get("furnished", False) is False

    def test_parse_text_fields(self):
        """Test text field parsing."""
        row = {
            "Название": "Квартира у моря",
            "Город": "Варна",
            "Описание": "Красивая квартира",
        }

        metadata = _parse_csv_row_metadata(row)

        assert metadata["title"] == "Квартира у моря"
        assert metadata["city"] == "Варна"
        assert metadata["description"] == "Красивая квартира"

    def test_parse_empty_values(self):
        """Test handling of empty values."""
        row = {
            "Цена (€)": "",
            "Комнат": "   ",
            "Город": "Варна",
        }

        metadata = _parse_csv_row_metadata(row)

        assert "price" not in metadata
        assert "rooms" not in metadata
        assert metadata["city"] == "Варна"

    def test_source_type_marker(self):
        """Test that source_type is always added."""
        row = {"Город": "Варна"}

        metadata = _parse_csv_row_metadata(row)

        assert metadata["source_type"] == "csv_row"


class TestChunkCSVWithDocling:
    """Test Docling-based CSV chunking path."""

    def test_docling_path_used_when_available(self):
        """Test that chunk_csv_by_rows uses Docling when available."""
        from src.ingestion.docling_client import DoclingChunk

        fake_chunks = [
            DoclingChunk(text="Row 1 content", seq_no=0),
            DoclingChunk(text="Row 2 content", seq_no=1),
        ]

        csv_content = "Название,Город\nRow1,City1\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()
            csv_path = Path(f.name)

        mock_adapter = MagicMock()
        mock_adapter.chunk_file_sync.return_value = fake_chunks
        mock_adapter.to_ingestion_chunks.return_value = [
            Chunk(
                text="Row 1 content",
                chunk_id=0,
                document_name="test.csv",
                article_number="abc123",
                order=0,
            ),
            Chunk(
                text="Row 2 content",
                chunk_id=1,
                document_name="test.csv",
                article_number="abc123",
                order=1,
            ),
        ]

        mock_module = MagicMock()
        mock_module.NativeDoclingAdapter.return_value = mock_adapter

        with patch.dict(
            "sys.modules",
            {"src.ingestion.docling_native": mock_module},
        ):
            chunks = chunk_csv_by_rows(csv_path, "test.csv")

        mock_module.NativeDoclingAdapter.assert_called_once()
        mock_adapter.chunk_file_sync.assert_called_once_with(csv_path)
        mock_adapter.to_ingestion_chunks.assert_called_once_with(
            fake_chunks, source="test.csv", source_type="csv"
        )
        assert len(chunks) == 2
        assert chunks[0].text == "Row 1 content"

    def test_fallback_to_legacy_on_import_error(self):
        """Test fallback to legacy when Docling import fails."""
        csv_content = """Название,Город,Цена (€)
Квартира,Варна,50000
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()
            csv_path = Path(f.name)

        mock_module = MagicMock()
        mock_module.NativeDoclingAdapter.side_effect = RuntimeError("docling not installed")

        with patch.dict(
            "sys.modules",
            {"src.ingestion.docling_native": mock_module},
        ):
            import warnings

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                chunks = chunk_csv_by_rows(csv_path, "test.csv")

            # Should have emitted a deprecation warning
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

        # Should still return chunks from legacy path
        assert len(chunks) == 1
        assert "Варна" in chunks[0].text

    def test_fallback_to_legacy_on_connection_error(self):
        """Test fallback when Docling adapter raises a connection error."""
        csv_content = """Название,Город
Row1,City1
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()
            csv_path = Path(f.name)

        mock_adapter = MagicMock()
        mock_adapter.chunk_file_sync.side_effect = RuntimeError(
            "docling is not installed"
        )

        mock_module = MagicMock()
        mock_module.NativeDoclingAdapter.return_value = mock_adapter

        with patch.dict(
            "sys.modules",
            {"src.ingestion.docling_native": mock_module},
        ):
            import warnings

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                chunks = chunk_csv_by_rows(csv_path, "test.csv")

            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

        assert len(chunks) == 1
        assert "City1" in chunks[0].text


class TestChunkCSVLegacy:
    """Test the legacy CSV chunking path directly."""

    def test_legacy_csv_chunking(self):
        """Test that _chunk_csv_legacy works as expected."""
        csv_content = """Название,Город,Цена (€),Комнат
Квартира 1,Варна,50000,2
Квартира 2,Бургас,75000,3
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()
            csv_path = Path(f.name)

        chunks = _chunk_csv_legacy(csv_path, "properties.csv")

        assert len(chunks) == 2
        assert "Варна" in chunks[0].text
        assert "Бургас" in chunks[1].text
        assert chunks[0].extra_metadata is not None
        assert chunks[0].extra_metadata.get("price") == 50000
