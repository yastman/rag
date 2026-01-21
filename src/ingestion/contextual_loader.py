"""Load contextual chunks into existing RAG pipeline.

Converts ContextualDocument objects (JSON from Claude CLI)
into Chunk objects compatible with DocumentIndexer.
"""

from .chunker import Chunk
from .contextual_schema import ContextualDocument


def load_contextual_chunks(doc: ContextualDocument) -> list[Chunk]:
    """
    Convert ContextualDocument to list of Chunk objects.

    Uses text_for_embedding (contextualized text) as the main text
    for BGE-M3 embedding. Preserves original text and metadata
    in extra_metadata for retrieval display.

    Args:
        doc: ContextualDocument from Claude CLI JSON output

    Returns:
        List of Chunk objects ready for DocumentIndexer
    """
    chunks: list[Chunk] = []

    for idx, ctx_chunk in enumerate(doc.chunks):
        chunk = Chunk(
            text=ctx_chunk.text_for_embedding,
            chunk_id=idx,
            document_name=doc.source,
            article_number=f"chunk_{ctx_chunk.chunk_id}",
            extra_metadata={
                "topic": ctx_chunk.topic,
                "keywords": ctx_chunk.keywords,
                "original_text": ctx_chunk.text,
                "context": ctx_chunk.context,
                "source_type": "vtt_contextual",
            },
        )
        chunks.append(chunk)

    return chunks


def load_contextual_json(json_path: str) -> list[Chunk]:
    """
    Load contextual chunks from JSON file.

    Convenience function that loads Claude CLI JSON output
    and converts to Chunks ready for indexing.

    Args:
        json_path: Path to JSON file created by Claude CLI

    Returns:
        List of Chunk objects ready for DocumentIndexer
    """
    doc = ContextualDocument.load(json_path)
    return load_contextual_chunks(doc)
