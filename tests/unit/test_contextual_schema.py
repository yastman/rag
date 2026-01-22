"""Unit tests for src/ingestion/contextual_schema.py."""

import json
import tempfile
from pathlib import Path

import pytest

from src.ingestion.contextual_schema import (
    ContextualChunk,
    ContextualDocument,
    create_text_for_embedding,
)


class TestCreateTextForEmbedding:
    """Test create_text_for_embedding function."""

    def test_creates_markdown_format(self):
        """Test that result is Markdown-formatted."""
        result = create_text_for_embedding(
            topic="Legal Topic",
            context="This discusses important legal matters.",
            text="The actual chunk text content.",
        )

        assert result.startswith("# Legal Topic")
        assert "This discusses important legal matters." in result
        assert "The actual chunk text content." in result

    def test_empty_context(self):
        """Test with empty context."""
        result = create_text_for_embedding(
            topic="Topic",
            context="",
            text="Text content",
        )

        assert "# Topic" in result
        assert "Text content" in result

    def test_whitespace_context(self):
        """Test with whitespace-only context."""
        result = create_text_for_embedding(
            topic="Topic",
            context="   ",
            text="Text",
        )

        # Should handle whitespace context
        assert "# Topic" in result


class TestContextualChunk:
    """Test ContextualChunk dataclass."""

    def test_chunk_creation(self):
        """Test basic ContextualChunk creation."""
        chunk = ContextualChunk(
            chunk_id=0,
            topic="Criminal Law",
            keywords=["crime", "punishment"],
            context="This chunk discusses criminal penalties.",
            text="Article 115 covers intentional homicide.",
        )

        assert chunk.chunk_id == 0
        assert chunk.topic == "Criminal Law"
        assert chunk.keywords == ["crime", "punishment"]
        assert chunk.context == "This chunk discusses criminal penalties."
        assert chunk.text == "Article 115 covers intentional homicide."

    def test_text_for_embedding_property(self):
        """Test text_for_embedding property generates formatted text."""
        chunk = ContextualChunk(
            chunk_id=1,
            topic="Property Law",
            keywords=["property", "ownership"],
            context="About ownership rights.",
            text="Property ownership details.",
        )

        embedding_text = chunk.text_for_embedding

        assert "# Property Law" in embedding_text
        assert "About ownership rights." in embedding_text
        assert "Property ownership details." in embedding_text

    def test_text_for_embedding_cached(self):
        """Test that text_for_embedding is cached."""
        chunk = ContextualChunk(
            chunk_id=2,
            topic="Test",
            keywords=[],
            context="Context",
            text="Text",
        )

        # First access
        text1 = chunk.text_for_embedding
        # Second access
        text2 = chunk.text_for_embedding

        assert text1 is text2  # Same object (cached)

    def test_to_dict(self):
        """Test chunk serialization to dict."""
        chunk = ContextualChunk(
            chunk_id=3,
            topic="Topic",
            keywords=["keyword1", "keyword2"],
            context="Context text",
            text="Main text",
        )

        result = chunk.to_dict()

        assert result["chunk_id"] == 3
        assert result["topic"] == "Topic"
        assert result["keywords"] == ["keyword1", "keyword2"]
        assert result["context"] == "Context text"
        assert result["text"] == "Main text"
        assert "text_for_embedding" in result

    def test_from_dict(self):
        """Test chunk deserialization from dict."""
        data = {
            "chunk_id": 4,
            "topic": "Loaded Topic",
            "keywords": ["key1"],
            "context": "Loaded context",
            "text": "Loaded text",
        }

        chunk = ContextualChunk.from_dict(data)

        assert chunk.chunk_id == 4
        assert chunk.topic == "Loaded Topic"
        assert chunk.keywords == ["key1"]
        assert chunk.context == "Loaded context"
        assert chunk.text == "Loaded text"

    def test_from_dict_with_embedding_text(self):
        """Test deserialization preserves cached embedding text."""
        data = {
            "chunk_id": 5,
            "topic": "Topic",
            "keywords": [],
            "context": "Context",
            "text": "Text",
            "text_for_embedding": "Pre-computed embedding text",
        }

        chunk = ContextualChunk.from_dict(data)

        # Should use pre-computed value
        assert chunk.text_for_embedding == "Pre-computed embedding text"


class TestContextualDocument:
    """Test ContextualDocument dataclass."""

    def test_document_creation(self):
        """Test basic ContextualDocument creation."""
        chunk = ContextualChunk(
            chunk_id=0,
            topic="Test",
            keywords=[],
            context="",
            text="Text",
        )

        doc = ContextualDocument(
            source="test.pdf",
            chunks=[chunk],
        )

        assert doc.source == "test.pdf"
        assert len(doc.chunks) == 1
        assert doc.processed_at is not None

    def test_total_chunks_property(self):
        """Test total_chunks property."""
        chunks = [
            ContextualChunk(chunk_id=i, topic="T", keywords=[], context="", text="T")
            for i in range(5)
        ]

        doc = ContextualDocument(source="doc.pdf", chunks=chunks)

        assert doc.total_chunks == 5

    def test_to_dict(self):
        """Test document serialization to dict."""
        chunk = ContextualChunk(
            chunk_id=0,
            topic="Topic",
            keywords=["k1"],
            context="Ctx",
            text="Txt",
        )
        doc = ContextualDocument(
            source="source.pdf",
            chunks=[chunk],
            processed_at="2024-01-01T00:00:00Z",
        )

        result = doc.to_dict()

        assert result["source"] == "source.pdf"
        assert result["total_chunks"] == 1
        assert result["processed_at"] == "2024-01-01T00:00:00Z"
        assert len(result["chunks"]) == 1

    def test_to_json(self):
        """Test document serialization to JSON."""
        chunk = ContextualChunk(
            chunk_id=0,
            topic="Topic",
            keywords=[],
            context="",
            text="Text",
        )
        doc = ContextualDocument(source="doc.pdf", chunks=[chunk])

        json_str = doc.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["source"] == "doc.pdf"

    def test_from_dict(self):
        """Test document deserialization from dict."""
        data = {
            "source": "loaded.pdf",
            "processed_at": "2024-01-01T00:00:00Z",
            "chunks": [
                {
                    "chunk_id": 0,
                    "topic": "T",
                    "keywords": [],
                    "context": "C",
                    "text": "X",
                }
            ],
        }

        doc = ContextualDocument.from_dict(data)

        assert doc.source == "loaded.pdf"
        assert doc.processed_at == "2024-01-01T00:00:00Z"
        assert len(doc.chunks) == 1
        assert doc.chunks[0].chunk_id == 0

    def test_from_json(self):
        """Test document deserialization from JSON string."""
        json_str = json.dumps(
            {
                "source": "json.pdf",
                "processed_at": "2024-01-01T00:00:00Z",
                "chunks": [
                    {
                        "chunk_id": 0,
                        "topic": "T",
                        "keywords": [],
                        "context": "C",
                        "text": "X",
                    }
                ],
            }
        )

        doc = ContextualDocument.from_json(json_str)

        assert doc.source == "json.pdf"
        assert len(doc.chunks) == 1

    def test_save_and_load(self):
        """Test saving and loading document from file."""
        chunk = ContextualChunk(
            chunk_id=0,
            topic="Test Topic",
            keywords=["kw1", "kw2"],
            context="Test context",
            text="Test text content",
        )
        doc = ContextualDocument(source="original.pdf", chunks=[chunk])

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "document.json"

            # Save
            doc.save(str(file_path))

            # Load
            loaded_doc = ContextualDocument.load(str(file_path))

            assert loaded_doc.source == "original.pdf"
            assert len(loaded_doc.chunks) == 1
            assert loaded_doc.chunks[0].topic == "Test Topic"
            assert loaded_doc.chunks[0].keywords == ["kw1", "kw2"]

    def test_roundtrip_serialization(self):
        """Test that serialization and deserialization are consistent."""
        chunks = [
            ContextualChunk(
                chunk_id=i,
                topic=f"Topic {i}",
                keywords=[f"kw{i}"],
                context=f"Context {i}",
                text=f"Text {i}",
            )
            for i in range(3)
        ]
        original = ContextualDocument(
            source="roundtrip.pdf",
            chunks=chunks,
            processed_at="2024-06-15T10:30:00Z",
        )

        # Roundtrip
        json_str = original.to_json()
        restored = ContextualDocument.from_json(json_str)

        assert restored.source == original.source
        assert restored.processed_at == original.processed_at
        assert len(restored.chunks) == len(original.chunks)

        for i, chunk in enumerate(restored.chunks):
            assert chunk.chunk_id == original.chunks[i].chunk_id
            assert chunk.topic == original.chunks[i].topic
            assert chunk.keywords == original.chunks[i].keywords
