"""Unit tests for src/ingestion/chunker.py."""

import tempfile
from pathlib import Path

import pytest

from src.ingestion.chunker import (
    Chunk,
    ChunkingStrategy,
    DocumentChunker,
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
        assert ChunkingStrategy.FIXED_SIZE.value == "fixed_size"
        assert ChunkingStrategy.SEMANTIC.value == "semantic"
        assert ChunkingStrategy.SLIDING_WINDOW.value == "sliding_window"


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
class TestDocumentChunkerFixedSize:
    """Test fixed-size chunking strategy (deprecated — see #780)."""

    def test_fixed_size_basic(self):
        """Test basic fixed-size chunking."""
        chunker = DocumentChunker(
            chunk_size=100,
            overlap=20,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )

        text = "A" * 200  # 200 characters
        chunks = chunker.chunk_text(text, "test.pdf", "1")

        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert chunks[0].document_name == "test.pdf"

    def test_fixed_size_overlap(self):
        """Test that chunks have correct overlap."""
        chunker = DocumentChunker(
            chunk_size=100,
            overlap=50,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )

        text = "A" * 150
        chunks = chunker.chunk_text(text, "test.pdf", "1")

        # With 100 chunk size and 50 overlap, step is 50
        # For 150 chars, we should get multiple chunks
        assert len(chunks) >= 2

    def test_fixed_size_small_text(self):
        """Test chunking text smaller than chunk_size."""
        chunker = DocumentChunker(
            chunk_size=1000,
            overlap=100,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )

        text = "Short text"
        chunks = chunker.chunk_text(text, "test.pdf", "1")

        assert len(chunks) == 1
        assert chunks[0].text == "Short text"

    def test_fixed_size_empty_text(self):
        """Test chunking empty text."""
        chunker = DocumentChunker(
            chunk_size=100,
            overlap=20,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )

        chunks = chunker.chunk_text("", "test.pdf", "1")

        assert len(chunks) == 0


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


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
class TestDocumentChunkerSlidingWindow:
    """Test sliding window chunking strategy (deprecated — see #780)."""

    def test_sliding_window_basic(self):
        """Test basic sliding window chunking."""
        chunker = DocumentChunker(
            chunk_size=100,
            overlap=50,
            strategy=ChunkingStrategy.SLIDING_WINDOW,
        )

        text = "A" * 200
        chunks = chunker.chunk_text(text, "test.pdf", "1")

        assert len(chunks) >= 3  # 200 chars, step=50, should get 4 windows

    def test_sliding_window_overlap_content(self):
        """Test that sliding windows actually overlap."""
        chunker = DocumentChunker(
            chunk_size=10,
            overlap=5,
            strategy=ChunkingStrategy.SLIDING_WINDOW,
        )

        text = "0123456789ABCDEFGHIJ"  # 20 chars
        chunks = chunker.chunk_text(text, "test.pdf", "1")

        # First chunk: 0-9, Second chunk: 5-14, etc.
        assert len(chunks) >= 3
        # Check overlap exists
        if len(chunks) >= 2:
            # Characters 5-9 should be in both first and second chunk
            assert "56789" in chunks[0].text
            assert "56789" in chunks[1].text


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
    """Test CSV row-based chunking."""

    def test_csv_chunking_basic(self):
        """Test basic CSV chunking."""
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

        assert len(chunks) == 2
        assert "Варна" in chunks[0].text
        assert "Бургас" in chunks[1].text

    def test_csv_chunking_metadata(self):
        """Test that CSV chunking extracts metadata."""
        csv_content = """Название,Город,Цена (€),Комнат,Площадь (м²)
Апартамент,Несебър,120000,3,85
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_content)
            f.flush()

            chunks = chunk_csv_by_rows(Path(f.name), "test.csv")

        assert len(chunks) == 1
        assert chunks[0].extra_metadata is not None
        assert chunks[0].extra_metadata.get("city") == "Несебър"
        assert chunks[0].extra_metadata.get("price") == 120000
        assert chunks[0].extra_metadata.get("rooms") == 3
        assert chunks[0].extra_metadata.get("area") == 85

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

        assert [c.chunk_id for c in chunks] == [0, 1, 2]
        assert [c.order for c in chunks] == [0, 1, 2]


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
