"""
Smoke test for chunking quality on Ukrainian legal documents.
Tests that DocumentChunker correctly handles legal text structure.
"""

import pytest

from src.ingestion.chunker import Chunk, ChunkingStrategy, DocumentChunker


pytestmark = pytest.mark.no_services


# Sample Ukrainian legal text with typical structural markers
SAMPLE_LEGAL_TEXT = """
Розділ I. ЗАГАЛЬНІ ПОЛОЖЕННЯ

Глава 1. Основні засади

Стаття 1. Завдання Кримінального кодексу України
Кримінальний кодекс України має своїм завданням правове забезпечення
охорони прав і свобод людини і громадянина, власності, громадського
порядку та громадської безпеки, довкілля, конституційного устрою України
від злочинних посягань, забезпечення миру і безпеки людства, а також
запобігання злочинам.

Стаття 2. Підстава кримінальної відповідальності
Підставою кримінальної відповідальності є вчинення особою суспільно
небезпечного діяння, яке містить склад злочину, передбаченого цим Кодексом.
Особа вважається невинуватою у вчиненні злочину і не може бути піддана
кримінальному покаранню, доки її вину не буде доведено в законному порядку.

Розділ II. ЗЛОЧИНИ ПРОТИ ЖИТТЯ ТА ЗДОРОВ'Я ОСОБИ

Глава 2. Злочини проти життя

Стаття 115. Умисне вбивство
1. Вбивство, тобто умисне протиправне заподіяння смерті іншій людині,
карається позбавленням волі на строк від семи до п'ятнадцяти років.
2. Умисне вбивство двох або більше осіб карається позбавленням волі
на строк від десяти до п'ятнадцяти років або довічним позбавленням волі.

Стаття 116. Умисне вбивство, вчинене в стані сильного душевного хвилювання
Умисне вбивство, вчинене в стані сильного душевного хвилювання, що раптово
виникло внаслідок протизаконного насильства, систематичного знущання або
тяжкої образи з боку потерпілого, карається обмеженням волі на строк
до п'яти років або позбавленням волі на той самий строк.
"""


@pytest.fixture
def semantic_chunker():
    """Create DocumentChunker with SEMANTIC strategy."""
    return DocumentChunker(
        chunk_size=512,
        overlap=50,
        strategy=ChunkingStrategy.SEMANTIC,
    )


@pytest.fixture
def chunks(semantic_chunker):
    """Generate chunks from sample legal text."""
    return semantic_chunker.chunk_text(
        text=SAMPLE_LEGAL_TEXT,
        document_name="criminal_code.pdf",
        article_number="1",
    )


class TestChunkingSmoke:
    """Smoke tests for chunking quality."""

    def test_chunks_are_produced(self, chunks):
        """Test that chunking produces at least one chunk."""
        assert len(chunks) > 0, "No chunks were produced from sample text"

    def test_chunks_have_nonempty_text(self, chunks):
        """Test that all chunks have non-empty text content."""
        for i, chunk in enumerate(chunks):
            assert chunk.text.strip(), f"Chunk {i} has empty text"

    def test_chunks_have_valid_metadata_fields(self, chunks):
        """Test that all chunks have required metadata fields populated."""
        for i, chunk in enumerate(chunks):
            assert isinstance(chunk, Chunk), f"Chunk {i} is not a Chunk instance"
            assert chunk.chunk_id is not None, f"Chunk {i} missing chunk_id"
            assert chunk.document_name == "criminal_code.pdf", (
                f"Chunk {i} has wrong document_name: {chunk.document_name}"
            )
            assert chunk.article_number is not None, f"Chunk {i} missing article_number"

    def test_chunk_sizes_are_reasonable(self, chunks):
        """Test that chunks have reasonable text lengths (not too short or too long)."""
        for i, chunk in enumerate(chunks):
            text_len = len(chunk.text)
            # Each chunk should have at least some meaningful content
            assert text_len >= 10, f"Chunk {i} is too short ({text_len} chars)"
            # No chunk should be excessively large (more than 3x chunk_size)
            assert text_len <= 3072, f"Chunk {i} is too large ({text_len} chars)"

    def test_semantic_strategy_respects_structure(self, semantic_chunker):
        """Test that SEMANTIC strategy splits on Ukrainian legal markers."""
        chunks = semantic_chunker.chunk_text(
            text=SAMPLE_LEGAL_TEXT,
            document_name="test_doc.pdf",
            article_number="1",
        )

        # The chunker should recognize Stattya/Rozdil/Hlava markers
        all_text = " ".join(c.text for c in chunks)
        assert "Стаття" in all_text, "Stattya marker not preserved in chunks"
        assert "Розділ" in all_text, "Rozdil marker not preserved in chunks"

        # Semantic splitting should produce chunk boundaries at structural markers
        assert any(c.text.startswith("Стаття") for c in chunks), (
            "No chunk starts with a structural marker - semantic splitting may not be working"
        )

    def test_extract_metadata_from_chunk_text(self, chunks):
        """Test that extract_metadata can parse article numbers from chunk text."""
        # At least one chunk should contain an article marker that extract_metadata can parse
        found_article = False
        for chunk in chunks:
            metadata = DocumentChunker.extract_metadata(chunk.text)
            if "article_number" in metadata:
                found_article = True
                # Parsed article number should be a numeric string
                assert metadata["article_number"].isdigit(), (
                    f"Extracted article_number is not numeric: {metadata['article_number']}"
                )
                break

        assert found_article, (
            "No chunk text contains a parseable article number - "
            "extract_metadata integration may be broken"
        )

    def test_chunk_ids_are_sequential(self, chunks):
        """Test that chunk IDs are assigned sequentially."""
        ids = [c.chunk_id for c in chunks]
        assert ids == list(range(len(chunks))), f"Chunk IDs are not sequential: {ids}"

    def test_chunk_order_matches_ids(self, chunks):
        """Test that chunk order field matches chunk_id."""
        for chunk in chunks:
            assert chunk.order == chunk.chunk_id, (
                f"Chunk order {chunk.order} does not match chunk_id {chunk.chunk_id}"
            )
