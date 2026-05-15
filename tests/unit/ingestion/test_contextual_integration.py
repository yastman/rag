"""Integration tests for Contextual Retrieval pipeline."""

from src.ingestion import (
    ContextualChunk,
    ContextualDocument,
    load_contextual_chunks,
    load_contextual_json,
)
from src.ingestion.chunker import Chunk


class TestContextualPipeline:
    """Test full pipeline from JSON to indexer-ready Chunks."""

    def test_json_round_trip(self, tmp_path):
        """Document should serialize and deserialize correctly."""
        doc = ContextualDocument(
            source="test.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Недвижимость в Болгарии",
                    keywords=["Болгария", "недвижимость", "покупка"],
                    context="Видео о покупке недвижимости в Болгарии.",
                    text="Покупка апартамента в Болгарии возле моря.",
                )
            ],
        )

        # Save
        json_file = tmp_path / "test.json"
        doc.save(str(json_file))

        # Load
        loaded = ContextualDocument.load(str(json_file))

        assert loaded.source == "test.vtt"
        assert len(loaded.chunks) == 1
        assert loaded.chunks[0].topic == "Недвижимость в Болгарии"

    def test_json_to_indexer_chunks(self, tmp_path):
        """JSON file should convert to indexer-compatible Chunks."""
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Цены",
                    keywords=["евро", "цены"],
                    context="Контекст о ценах.",
                    text="50000 евро за студию.",
                ),
                ContextualChunk(
                    chunk_id=2,
                    topic="Локации",
                    keywords=["Бургас", "море"],
                    context="Контекст о локациях.",
                    text="Бургас у моря.",
                ),
            ],
        )

        # Save and load via function
        json_file = tmp_path / "video.json"
        doc.save(str(json_file))
        chunks = load_contextual_json(str(json_file))

        assert len(chunks) == 2
        assert all(isinstance(c, Chunk) for c in chunks)

        # Check first chunk
        assert "# Цены" in chunks[0].text
        assert chunks[0].extra_metadata["topic"] == "Цены"
        assert chunks[0].document_name == "video.vtt"

    def test_text_for_embedding_format(self):
        """text_for_embedding should be properly formatted Markdown."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Недвижимость в Болгарии",
            keywords=["Болгария"],
            context="Этот фрагмент из видео о покупке недвижимости.",
            text="Покупка апартамента возле моря.",
        )

        text = chunk.text_for_embedding

        # Should be Markdown format
        lines = text.split("\n")
        assert lines[0] == "# Недвижимость в Болгарии"
        assert "Этот фрагмент из видео" in text
        assert "Покупка апартамента" in text

    def test_metadata_preserved_for_search_display(self):
        """Original text should be in metadata for search result display."""
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[
                ContextualChunk(
                    chunk_id=1,
                    topic="Тема",
                    keywords=["ключ"],
                    context="Контекст для embedding.",
                    text="Оригинальный текст для отображения.",
                )
            ],
        )

        chunks = load_contextual_chunks(doc)

        # text_for_embedding used for vectorization
        assert "# Тема" in chunks[0].text
        assert "Контекст для embedding" in chunks[0].text

        # Original text preserved for display
        assert chunks[0].extra_metadata["original_text"] == "Оригинальный текст для отображения."


class TestExampleJson:
    """Test with example JSON structure."""

    def test_parses_example_json(self, tmp_path):
        """Should parse JSON in documented format."""
        example_json = """{
  "source": "Как купить квартиру в Болгарии.vtt",
  "processed_at": "2026-01-21T12:00:00",
  "total_chunks": 2,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Введение в покупку недвижимости",
      "keywords": ["Болгария", "недвижимость", "покупка"],
      "context": "Вступительная часть видео о покупке недвижимости.",
      "text": "Покупка апартамента в Болгарии возле моря.",
      "text_for_embedding": "# Введение\\n\\nВступительная часть\\n\\nПокупка апартамента"
    },
    {
      "chunk_id": 2,
      "topic": "Цены на недвижимость",
      "keywords": ["цены", "евро", "Бургас"],
      "context": "Обсуждение цен на квартиры в разных городах.",
      "text": "В Бургасе цены начинаются от 50000 евро.",
      "text_for_embedding": "# Цены\\n\\nОбсуждение цен\\n\\nВ Бургасе цены"
    }
  ]
}"""
        json_file = tmp_path / "example.json"
        json_file.write_text(example_json, encoding="utf-8")

        chunks = load_contextual_json(str(json_file))

        assert len(chunks) == 2
        assert chunks[0].extra_metadata["topic"] == "Введение в покупку недвижимости"
        assert chunks[1].extra_metadata["topic"] == "Цены на недвижимость"
        assert "Бургас" in chunks[1].extra_metadata["keywords"]
