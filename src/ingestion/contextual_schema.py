"""JSON schema for Contextual Retrieval chunks.

Defines dataclasses for storing contextualized chunks created by Claude CLI:
- LLM-generated context (Anthropic Contextual Retrieval)
- Extracted metadata (topic, keywords)
- Formatted text for embedding

Claude CLI creates JSON in this format, Python code loads and indexes it.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def create_text_for_embedding(topic: str, context: str, text: str) -> str:
    """
    Create Markdown-formatted text for embedding.

    Format:
    # {topic}

    {context}

    {text}

    Args:
        topic: Main topic of the chunk
        context: LLM-generated context
        text: Original chunk text

    Returns:
        Formatted Markdown string
    """
    parts = [f"# {topic}"]

    if context and context.strip():
        parts.append(f"\n{context}")

    parts.append(f"\n{text}")

    return "\n".join(parts)


@dataclass
class ContextualChunk:
    """A chunk with LLM-generated context and metadata.

    Created by Claude CLI during Contextual Retrieval processing.
    """

    chunk_id: int
    topic: str
    keywords: list[str]
    context: str
    text: str
    _text_for_embedding: Optional[str] = field(default=None, repr=False)

    @property
    def text_for_embedding(self) -> str:
        """Get or generate text formatted for embedding."""
        if self._text_for_embedding is None:
            self._text_for_embedding = create_text_for_embedding(
                topic=self.topic,
                context=self.context,
                text=self.text,
            )
        return self._text_for_embedding

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "topic": self.topic,
            "keywords": self.keywords,
            "context": self.context,
            "text": self.text,
            "text_for_embedding": self.text_for_embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextualChunk":
        """Deserialize from dictionary."""
        return cls(
            chunk_id=data["chunk_id"],
            topic=data["topic"],
            keywords=data["keywords"],
            context=data["context"],
            text=data["text"],
            _text_for_embedding=data.get("text_for_embedding"),
        )


@dataclass
class ContextualDocument:
    """A document with contextualized chunks.

    JSON file created by Claude CLI, loaded by Python for indexing.
    """

    source: str
    chunks: list[ContextualChunk]
    processed_at: Optional[str] = None

    def __post_init__(self):
        if self.processed_at is None:
            self.processed_at = datetime.now(timezone.utc).isoformat()

    @property
    def total_chunks(self) -> int:
        """Total number of chunks."""
        return len(self.chunks)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "source": self.source,
            "processed_at": self.processed_at,
            "total_chunks": self.total_chunks,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, file_path: str) -> None:
        """Save to JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: dict) -> "ContextualDocument":
        """Deserialize from dictionary."""
        chunks = [ContextualChunk.from_dict(c) for c in data["chunks"]]
        return cls(
            source=data["source"],
            chunks=chunks,
            processed_at=data.get("processed_at"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ContextualDocument":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def load(cls, file_path: str) -> "ContextualDocument":
        """Load from JSON file."""
        with open(file_path, encoding="utf-8") as f:
            return cls.from_json(f.read())
