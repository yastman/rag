#!/usr/bin/env python3
"""
Contextual Retrieval + Knowledge Graph Ingestion Pipeline
Complete implementation with testing support
"""

import sys
import time

import requests
from contextualize_zai import ContextualRetrievalZAI

from config import (
    BGE_M3_TIMEOUT,
    BGE_M3_URL,
    CHUNK_PROCESSING_DELAY,
    COLLECTION_CONTEXTUAL_KG,
    DOCLING_TIMEOUT,
    DOCLING_URL,
    DOCUMENT_NAME,
    PDF_PATH,
    QDRANT_API_KEY,
    QDRANT_URL,
    TEST_MAX_CHUNKS,
    ZAI_API_KEY,
    validate_config,
)
from utils.structure_parser import add_graph_edges


def print_header(text: str):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def print_step(num: int, text: str):
    print(f"\n{'─' * 80}")
    print(f"STEP {num}: {text}")
    print("─" * 80)


def print_info(text: str, indent: int = 1):
    print("  " * indent + f"✓ {text}")


def print_progress(current: int, total: int, text: str = ""):
    bar_len = 50
    filled = int(bar_len * current / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    percent = (current / total) * 100
    print(f"\r  [{bar}] {percent:5.1f}% ({current}/{total}) {text}", end="", flush=True)


def docling_chunk(pdf_path: str) -> dict:
    """Step 1: Chunk document with Docling."""
    with open(pdf_path, "rb") as f:
        response = requests.post(
            f"{DOCLING_URL}/v1/chunk/hybrid/file", files={"files": f}, timeout=DOCLING_TIMEOUT
        )
    response.raise_for_status()
    return response.json()


def get_full_document_text(pdf_path: str) -> str:
    """Get full document text for Claude prompt caching."""
    # For now, use Docling to get full text
    # In production, might want to cache this separately
    with open(pdf_path, "rb") as f:
        response = requests.post(
            f"{DOCLING_URL}/v1/chunk/hybrid/file", files={"files": f}, timeout=DOCLING_TIMEOUT
        )
    response.raise_for_status()
    data = response.json()

    # Concatenate all chunks to get full document
    return "\n\n".join([chunk["text"] for chunk in data["chunks"]])


def bge_m3_encode(text: str) -> dict:
    """Encode text with BGE-M3 (returns dense + sparse + colbert)."""
    response = requests.post(
        f"{BGE_M3_URL}/encode/hybrid", json={"texts": [text]}, timeout=BGE_M3_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def qdrant_upsert(collection: str, point_id: int, vectors: dict, payload: dict):
    """Insert point into Qdrant."""
    data = {"points": [{"id": point_id, "vector": vectors, "payload": payload}]}

    response = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        json=data,
        headers={"api-key": QDRANT_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def process_document_contextual_kg(
    pdf_path: str,
    collection_name: str,
    max_chunks: int | None = None,
    document_name: str = DOCUMENT_NAME,
):
    """
    Full ingestion pipeline with Contextual Retrieval + KG.

    Args:
        pdf_path: Path to PDF file
        collection_name: Qdrant collection name
        max_chunks: Limit chunks for testing (None = process all)
        document_name: Name of the document
    """
    print_header("🚀 CONTEXTUAL RETRIEVAL + KG INGESTION PIPELINE")
    print_info(f"Document: {document_name}", 0)
    print_info(f"PDF Path: {pdf_path}", 0)
    print_info(f"Collection: {collection_name}", 0)
    print_info(f"Max chunks: {max_chunks or 'ALL'}", 0)

    start_time = time.time()

    # Initialize contextualizer
    print_step(0, "INITIALIZATION")
    try:
        contextualizer = ContextualRetrievalZAI(api_key=ZAI_API_KEY, rate_limit_delay=1.2)
        print_info("ContextualRetrievalZAI initialized (Z.AI GLM-4.6)")
        print_info("Fallback mode: Will use regex parser if API fails")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to initialize ContextualRetrievalZAI: {e}")
        print("Make sure ZAI_API_KEY is set!")
        return False

    # Step 1: Docling chunking
    print_step(1, "DOCLING CHUNKING")
    try:
        doc_data = docling_chunk(pdf_path)
        chunks = doc_data["chunks"]
        print_info(f"Total chunks: {len(chunks)}")
        print_info(f"Processing time: {doc_data['processing_time']:.2f}s")

        # Limit for testing
        if max_chunks:
            chunks = chunks[:max_chunks]
            print_info(f"Limited to {max_chunks} chunks for testing")

    except Exception as e:
        print(f"\n❌ ERROR: Docling chunking failed: {e}")
        return False

    # Get full document text (for prompt caching)
    print_step(2, "LOADING FULL DOCUMENT (for caching)")
    try:
        doc_content = get_full_document_text(pdf_path)
        print_info(f"Document length: {len(doc_content)} characters")
        print_info("This will be cached by Claude API (90% cost savings)")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to load document: {e}")
        return False

    # Step 3: Process each chunk
    print_step(3, "CONTEXTUAL EMBEDDING + KG EXTRACTION")
    print()

    stats = {"total": len(chunks), "success": 0, "failed": 0, "start": time.time()}

    for idx, chunk in enumerate(chunks):
        chunk_id = idx + 1
        chunk_text = chunk["text"]

        print_progress(idx + 1, len(chunks), f"Chunk {chunk_id}")

        try:
            # Generate context + extract metadata (Claude API)
            context_text, metadata = contextualizer.situate_context_with_metadata(
                doc_content=doc_content, chunk_text=chunk_text, document_name=document_name
            )

            # Add graph edges
            metadata = add_graph_edges(metadata)

            # Prepare contextualized text for embedding
            embedded_text = f"{context_text}\n\n{chunk_text}"

            # Embed with BGE-M3
            embeddings = bge_m3_encode(embedded_text)

            # Prepare Qdrant payload
            payload = {
                # Original content (for display)
                "text": chunk_text,
                # Contextual Retrieval
                "contextual_prefix": context_text,
                "embedded_text": embedded_text,
                # Knowledge Graph metadata
                "document": document_name,
                **metadata,  # All KG metadata (book, section, chapter, article, etc.)
                # Source tracking
                "source": pdf_path,
                "chunk_index": idx,
            }

            # Prepare vectors
            vectors = {
                "dense": embeddings["dense_vecs"][0],
                "sparse": {
                    "indices": embeddings["lexical_weights"][0]["indices"],
                    "values": embeddings["lexical_weights"][0]["values"],
                },
                "colbert": embeddings["colbert_vecs"][0],
            }

            # Insert into Qdrant
            qdrant_upsert(collection_name, chunk_id, vectors, payload)

            stats["success"] += 1

        except Exception as e:
            stats["failed"] += 1
            print(f"\n  ✗ Chunk {chunk_id} failed: {e}")
            continue

        # Rate limiting
        time.sleep(CHUNK_PROCESSING_DELAY)

    print()  # Complete progress line
    stats["elapsed"] = time.time() - stats["start"]

    # Print statistics
    print("\n  📊 Processing Statistics:")
    print_info(f"Total chunks: {stats['total']}", 2)
    print_info(f"Success: {stats['success']}", 2)
    print_info(f"Failed: {stats['failed']}", 2)
    print_info(f"Total time: {stats['elapsed']:.2f}s", 2)
    print_info(f"Avg per chunk: {stats['elapsed'] / stats['total']:.2f}s", 2)

    # Print contextualizer stats
    contextualizer.print_stats()

    # Verify collection
    print_step(4, "VERIFICATION")
    try:
        response = requests.get(
            f"{QDRANT_URL}/collections/{collection_name}", headers={"api-key": QDRANT_API_KEY}
        )
        response.raise_for_status()
        collection_info = response.json()["result"]

        print_info(f"Collection: {collection_name}")
        print_info(f"Points count: {collection_info['points_count']}")
        print_info(
            f"Vectors config: {', '.join(collection_info['config']['params']['vectors'].keys())}"
        )

        if collection_info["points_count"] == stats["success"]:
            print_info("✅ Point count matches successful inserts!")
        else:
            print(
                f"  ⚠️  WARNING: Point count mismatch ({collection_info['points_count']} != {stats['success']})"
            )

    except Exception as e:
        print(f"\n  ⚠️  WARNING: Could not verify collection: {e}")

    # Final summary
    total_time = time.time() - start_time
    print_header("✅ INGESTION COMPLETED")
    print_info(f"Total duration: {total_time:.2f}s", 0)
    print_info(f"Chunks processed: {stats['success']}/{stats['total']}", 0)
    print_info(f"Collection: {collection_name}", 0)
    print("=" * 80)

    return stats["failed"] == 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Contextual RAG Ingestion Pipeline")
    parser.add_argument("--test", action="store_true", help="Test mode (5 chunks)")
    parser.add_argument("--max-chunks", type=int, help="Max chunks to process")
    parser.add_argument("--collection", default=COLLECTION_CONTEXTUAL_KG, help="Collection name")
    parser.add_argument("--pdf", default=PDF_PATH, help="PDF file path")

    args = parser.parse_args()

    # Validate config
    if not validate_config():
        sys.exit(1)

    # Determine max chunks
    max_chunks = TEST_MAX_CHUNKS if args.test else args.max_chunks

    # Create collection
    print_header("STEP 0: CREATE COLLECTION")
    from create_collection_enhanced import create_enhanced_collection

    try:
        create_enhanced_collection(args.collection)
    except Exception as e:
        print(f"❌ ERROR: Failed to create collection: {e}")
        sys.exit(1)

    # Run ingestion
    success = process_document_contextual_kg(
        pdf_path=args.pdf, collection_name=args.collection, max_chunks=max_chunks
    )

    sys.exit(0 if success else 1)
