#!/usr/bin/env python3
"""Universal document indexer for Qdrant (PDF, DOCX, CSV, XLSX, etc.)

Usage:
    python simple_index_test.py file1.pdf file2.docx --collection my_docs
    python simple_index_test.py demo_BG.csv info_bg_home.docx --collection bulgarian_properties
"""

import argparse
import asyncio
from pathlib import Path

from src.config import Settings
from src.ingestion.chunker import DocumentChunker
from src.ingestion.document_parser import UniversalDocumentParser
from src.ingestion.indexer import DocumentIndexer


async def main():
    """Index documents to Qdrant with BGE-M3 (dense + BM42 sparse + ColBERT)."""
    parser = argparse.ArgumentParser(description="Index documents to Qdrant")
    parser.add_argument("files", nargs="+", help="Files to index (PDF, DOCX, CSV, XLSX)")
    parser.add_argument("--collection", default="documents", help="Collection name")
    parser.add_argument("--recreate", action="store_true", help="Recreate collection")
    parser.add_argument("--chunk-size", type=int, default=1024, help="Chunk size")
    parser.add_argument("--overlap", type=int, default=256, help="Chunk overlap")
    args = parser.parse_args()

    print("=" * 80)
    print("Universal Document Indexer → Qdrant")
    print("=" * 80)
    print(f"Files: {len(args.files)}")
    print(f"Collection: {args.collection}")
    print("Embeddings: BGE-M3 (dense 1024-dim + BM42 sparse + ColBERT)")
    print("Format: n8n/LangChain compatible (page_content + metadata)")
    print("=" * 80)
    print()

    # Initialize
    settings = Settings()
    doc_parser = UniversalDocumentParser(use_cache=True)
    chunker = DocumentChunker(chunk_size=args.chunk_size, overlap=args.overlap)
    indexer = DocumentIndexer(settings)

    # Create collection
    if args.recreate:
        print(f"Creating collection: {args.collection}...")
        indexer.create_collection(args.collection, recreate=True)
        print()

    # Process all files
    all_chunks = []
    for file_path_str in args.files:
        file_path = Path(file_path_str)
        if not file_path.exists():
            print(f"⚠️  File not found: {file_path}")
            continue

        # Parse
        print(f"📄 Parsing: {file_path.name}...")
        parsed_doc = doc_parser.parse_file(file_path)
        print(f"   ✓ {len(parsed_doc.content):,} chars", end="")
        if parsed_doc.num_pages:
            print(f", {parsed_doc.num_pages} pages")
        else:
            print()

        # Chunk
        file_chunks = chunker.chunk_text(
            text=parsed_doc.content,
            document_name=parsed_doc.filename,
            article_number=file_path.stem,
        )
        print(f"   ✓ {len(file_chunks)} chunks")
        all_chunks.extend(file_chunks)

    print()
    print(f"Total chunks: {len(all_chunks)}")
    print()

    # Index
    print(f"Indexing to {args.collection}...")
    stats = await indexer.index_chunks(all_chunks, args.collection, batch_size=8)
    print()

    # Results
    print("=" * 80)
    print("✅ INDEXING COMPLETE")
    print("=" * 80)
    print(f"Total chunks: {stats.total_chunks}")
    print(f"Indexed: {stats.indexed_chunks}")
    print(f"Failed: {stats.failed_chunks}")
    print()

    # Verify
    coll_stats = indexer.get_collection_stats(args.collection)
    print(f"Collection: {args.collection}")
    print(f"Points: {coll_stats.get('points_count', 0)}")
    print(f"Vectors: {coll_stats.get('vectors_count', 0)}")
    print()
    print("✓ Ready for n8n/LangChain!")
    print()


if __name__ == "__main__":
    asyncio.run(main())
