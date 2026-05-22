"""Tests for Contextual Retrieval JSON schema."""

import json

from src.ingestion.contextual_schema import (
    ContextualChunk,
    ContextualDocument,
    create_text_for_embedding,
)


class TestContextualChunk:
    """Tests for ContextualChunk dataclass."""

    def test_chunk_creation(self):
        """Chunk should store all required fields."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Цены на недвижимость",
            keywords=["Бургас", "цены", "евро"],
            context="Этот фрагмент о ценах на квартиры в Болгарии.",
            text="В Бургасе цены начинаются от 50000 евро.",
        )
        assert chunk.chunk_id == 1
        assert chunk.topic == "Цены на недвижимость"
        assert len(chunk.keywords) == 3
        assert "Бургас" in chunk.keywords

    def test_chunk_text_for_embedding(self):
        """text_for_embedding should combine context and text."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["слово"],
            context="Контекст чанка.",
            text="Основной текст.",
        )
        embedding_text = chunk.text_for_embedding
        assert "# Тема" in embedding_text
        assert "Контекст чанка." in embedding_text
        assert "Основной текст." in embedding_text

    def test_chunk_to_dict(self):
        """Chunk should serialize to dict."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["a", "b"],
            context="Контекст",
            text="Текст",
        )
        d = chunk.to_dict()
        assert d["chunk_id"] == 1
        assert d["topic"] == "Тема"
        assert "text_for_embedding" in d


class TestContextualDocument:
    """Tests for ContextualDocument dataclass."""

    def test_document_creation(self):
        """Document should store source and chunks."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["слово"],
            context="Контекст",
            text="Текст",
        )
        doc = ContextualDocument(
            source="video.vtt",
            chunks=[chunk],
        )
        assert doc.source == "video.vtt"
        assert len(doc.chunks) == 1
        assert doc.total_chunks == 1

    def test_document_to_json(self):
        """Document should serialize to valid JSON."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Тема",
            keywords=["слово"],
            context="Контекст",
            text="Текст",
        )
        doc = ContextualDocument(source="video.vtt", chunks=[chunk])
        json_str = doc.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["source"] == "video.vtt"
        assert parsed["total_chunks"] == 1
        assert "processed_at" in parsed

    def test_document_from_json(self):
        """Document should deserialize from JSON."""
        json_str = """{
            "source": "test.vtt",
            "processed_at": "2026-01-21T12:00:00",
            "total_chunks": 1,
            "chunks": [{
                "chunk_id": 1,
                "topic": "Тема",
                "keywords": ["a"],
                "context": "Контекст",
                "text": "Текст",
                "text_for_embedding": "# Тема\\n\\nКонтекст\\n\\nТекст"
            }]
        }"""
        doc = ContextualDocument.from_json(json_str)
        assert doc.source == "test.vtt"
        assert len(doc.chunks) == 1
        assert doc.chunks[0].topic == "Тема"


class TestCreateTextForEmbedding:
    """Tests for text_for_embedding generation."""

    def test_creates_markdown_format(self):
        """Should create Markdown-formatted text."""
        result = create_text_for_embedding(
            topic="Цены в Бургасе",
            context="Обсуждение цен на недвижимость.",
            text="Цены начинаются от 50000 евро.",
        )
        assert result.startswith("# Цены в Бургасе")
        assert "Обсуждение цен" in result
        assert "50000 евро" in result

    def test_handles_empty_context(self):
        """Should handle empty context gracefully."""
        result = create_text_for_embedding(
            topic="Тема",
            context="",
            text="Текст чанка.",
        )
        assert "# Тема" in result
        assert "Текст чанка." in result
