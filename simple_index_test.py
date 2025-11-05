#!/usr/bin/env python3
"""Universal document indexer for Qdrant (PDF, DOCX, CSV, XLSX, etc.)

Usage:
    python simple_index_test.py file1.pdf file2.docx --collection my_docs
    python simple_index_test.py demo_BG.csv info_bg_home.docx --collection bulgarian_properties
"""

import argparse
import asyncio
import logging
from pathlib import Path

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter

from src.config import Settings
from src.ingestion.indexer import DocumentIndexer


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

# Set specific loggers
logging.getLogger("src.ingestion.indexer").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # Suppress HTTP logs


async def main():
    """Index documents to Qdrant with BGE-M3 (dense + BM42 sparse + ColBERT)."""
    parser = argparse.ArgumentParser(description="Index documents to Qdrant")
    parser.add_argument("files", nargs="+", help="Files to index (PDF, DOCX, CSV, XLSX)")
    parser.add_argument("--collection", default="documents", help="Collection name")
    parser.add_argument("--recreate", action="store_true", help="Recreate collection")
    parser.add_argument(
        "--max-tokens", type=int, default=512, help="Max tokens per chunk (default: 512 for BGE-M3)"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Universal Document Indexer → Qdrant")
    print("=" * 80)
    print(f"Files: {len(args.files)}")
    print(f"Collection: {args.collection}")
    print("Embeddings: BGE-M3 (dense 1024-dim + BM42 sparse + ColBERT)")
    print(f"Chunking: Docling HybridChunker (max {args.max_tokens} tokens)")
    print("Format: n8n/LangChain compatible (page_content + metadata)")
    print("=" * 80)
    print()

    # Initialize
    settings = Settings()
    indexer = DocumentIndexer(settings)

    # Initialize Docling DocumentConverter and HybridChunker
    print("Initializing Docling DocumentConverter and HybridChunker...")
    doc_converter = DocumentConverter()
    chunker = HybridChunker(
        tokenizer="BAAI/bge-m3",  # HybridChunker accepts model ID directly
        max_tokens=args.max_tokens,
    )
    print(f"✓ Initialized (max_tokens={args.max_tokens})")
    print()

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

        # CSV files: use row-based chunking (1 row = 1 chunk)
        if file_path.suffix.lower() == ".csv":
            print(f"📄 Processing CSV: {file_path.name}...")
            from src.ingestion.chunker import chunk_csv_by_rows

            csv_chunks = chunk_csv_by_rows(file_path, file_path.name)
            print(f"   ✓ {len(csv_chunks)} rows → {len(csv_chunks)} chunks")
            all_chunks.extend(csv_chunks)
            continue

        # Other files: use Docling + HybridChunker
        print(f"📄 Converting: {file_path.name}...")
        result = doc_converter.convert(file_path)
        dl_doc = result.document

        # Export to markdown to get character count
        md_content = dl_doc.export_to_markdown()
        print(f"   ✓ {len(md_content):,} chars")

        # Chunk with HybridChunker
        doc_chunks = list(chunker.chunk(dl_doc))
        print(f"   ✓ {len(doc_chunks)} chunks")

        # Convert HybridChunker chunks to our Chunk format
        from src.ingestion.chunker import Chunk

        for i, hybrid_chunk in enumerate(doc_chunks):
            chunk = Chunk(
                text=hybrid_chunk.text,
                chunk_id=i,
                document_name=file_path.name,
                article_number=file_path.stem,
                order=i,
            )
            all_chunks.append(chunk)

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
