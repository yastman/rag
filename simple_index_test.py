#!/usr/bin/env python3
"""Simple indexing test with CK.pdf."""

import asyncio
from pathlib import Path

from src.config import Settings
from src.ingestion.chunker import DocumentChunker
from src.ingestion.document_parser import UniversalDocumentParser
from src.ingestion.indexer import DocumentIndexer


async def main():
    """Index CK.pdf to legal_documents collection."""
    print("=" * 80)
    print("Simple Indexing Test: CK.pdf")
    print("=" * 80)
    print()

    # Initialize
    settings = Settings()
    parser = UniversalDocumentParser()
    chunker = DocumentChunker(chunk_size=1024, overlap=256)
    indexer = DocumentIndexer(settings)

    # Parse PDF
    pdf_path = Path("/srv/CK.pdf")
    print(f"Parsing: {pdf_path.name}...")
    parsed_doc = parser.parse_file(pdf_path)
    print(f"✓ Parsed: {parsed_doc.num_pages} pages")
    print(f"  Title: {parsed_doc.title}")
    print(f"  Content length: {len(parsed_doc.content)} chars")
    print()

    # Chunk content
    print("Chunking...")
    chunks = chunker.chunk_text(
        text=parsed_doc.content,
        document_name=parsed_doc.filename,
        article_number="CK",  # Default article number
    )
    print(f"✓ Created {len(chunks)} chunks")
    if chunks:
        print(f"  First chunk: {chunks[0].text[:100]}...")
    print()

    # Index
    print("Indexing to Qdrant...")
    stats = await indexer.index_chunks(chunks, "legal_documents")
    print(f"✓ Indexed {stats.indexed_chunks}/{stats.total_chunks} chunks")
    print()

    # Verify
    print("Collection stats:")
    coll_stats = indexer.get_collection_stats("legal_documents")
    print(f"  Points: {coll_stats.get('points_count', 0)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
