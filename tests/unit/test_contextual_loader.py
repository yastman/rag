"""Tests for loading contextual chunks into existing pipeline."""

from src.ingestion.chunker import Chunk
from src.ingestion.contextual_loader import load_contextual_chunks, load_contextual_json
from src.ingestion.contextual_schema import ContextualChunk, ContextualDocument


class TestLoadContextualChunks:
    """Tests for load_contextual_chunks function."""

    def test_converts_to_chunk_objects(self):
        """Should convert ContextualDocument to list of Chunk objects."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Тема",
                    keywords=["слово"],
                    context="Контекст",
                    text="Текст",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        assert len(chunks) == 1
        assert isinstance(chunks[0], Chunk)

    def test_uses_text_for_embedding(self):
        """Chunk.text should be the contextualized text_for_embedding."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Цены",
                    keywords=["евро"],
                    context="Контекст о ценах.",
                    text="50000 евро.",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        # Should use text_for_embedding, not raw text
        assert "# Цены" in chunks[0].text
        assert "Контекст о ценах" in chunks[0].text
        assert "50000 евро" in chunks[0].text

    def test_preserves_metadata(self):
        """extra_metadata should contain topic, keywords, original_text."""
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Недвижимость",
                    keywords=["Болгария", "цены"],
                    context="Контекст",
                    text="Оригинальный текст",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        meta = chunks[0].extra_metadata
        assert meta["topic"] == "Недвижимость"
        assert meta["keywords"] == ["Болгария", "цены"]
        assert meta["original_text"] == "Оригинальный текст"
        assert meta["context"] == "Контекст"
        assert meta["source_type"] == "vtt_contextual"

    def test_sets_document_name(self):
        """document_name should be the source filename."""
        doc = ContextualDocument(
            source="my_video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="T",
                    keywords=["k"],
                    context="C",
                    text="X",
                )
            ],
        )
        chunks = load_contextual_chunks(doc)

        assert chunks[0].document_name == "my_video.vtt"

    def test_handles_multiple_chunks(self):
        """Should handle documents with multiple chunks."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=i, topic=f"T{i}", keywords=[], context="", text=f"Text {i}"
                )
                for i in range(5)
            ],
        )
        chunks = load_contextual_chunks(doc)

        assert len(chunks) == 5
        assert chunks[0].chunk_id == 0
        assert chunks[4].chunk_id == 4


class TestLoadContextualJson:
    """Tests for load_contextual_json function."""

    def test_loads_from_file(self, tmp_path):
        """Should load JSON file and convert to Chunks."""
        # Create test JSON
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Тест",
                    keywords=["test"],
                    context="Test context",
                    text="Test text",
                )
            ],
        )
        json_file = tmp_path / "test.json"
        doc.save(str(json_file))

        # Load and convert
        chunks = load_contextual_json(str(json_file))

        assert len(chunks) == 1
        assert isinstance(chunks[0], Chunk)
        assert "# Тест" in chunks[0].text
