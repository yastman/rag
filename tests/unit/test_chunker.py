"""Unit tests for src/ingestion/chunker.py."""

import pytest

from src.ingestion.chunker import (
    Chunk,
    ChunkingStrategy,
    DocumentChunker,
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
        # FIXED_SIZE and SLIDING_WINDOW were removed in #1235 (no production
        # callers; emitted DeprecationWarning since #780).
        assert not hasattr(ChunkingStrategy, "FIXED_SIZE")
        assert not hasattr(ChunkingStrategy, "SLIDING_WINDOW")


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


# ``chunk_csv_by_rows`` and ``_parse_csv_row_metadata`` were removed in the
# #1235 CSV slice. They had zero production callers — the apartments ingest
# path uses ``src/ingestion/apartments/source.py`` with its own
# ``csv.DictReader`` flow. Their absence is pinned by
# ``tests/contract/test_chunking_strategy_sdk_native_contract.py``.
