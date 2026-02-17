#!/usr/bin/env python3
"""
FAST Contextual Retrieval + KG Ingestion Pipeline
Async parallel processing = 15-50x speedup

MLflow Integration (2025):
- Tracks all ingestion experiments
- Logs config, metrics, artifacts
- Enables A/B testing (chunk sizes, context vs no context)
"""

import asyncio
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import requests
from contextualize_zai_async import ContextualRetrievalZAIAsync


# Add src/ to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    BGE_M3_TIMEOUT,
    BGE_M3_URL,
    DOCLING_TIMEOUT,
    DOCLING_URL,
    DOCUMENT_NAME,
    PDF_PATH,
    QDRANT_API_KEY,
    QDRANT_URL,
    TEST_MAX_CHUNKS,
    ZAI_API_KEY,
)
from src.evaluation.mlflow_integration import MLflowRAGLogger
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


def detect_tables_heuristic(text: str) -> bool:
    """
    Fast heuristic to detect REAL tables (not legal document structure).

    Args:
        text: Sample text from PDF

    Returns:
        True if tables likely present
    """
    text_lower = text.lower()

    # NEGATIVE indicators: Legal document structure (NOT tables)
    legal_keywords = [
        "стаття",
        "статья",  # Article
        "розділ",
        "раздел",  # Section
        "глава",  # Chapter
        "книга",  # Book
        "кодекс",
        "кодекса",  # Code
    ]

    # If document is clearly legal structure → NOT a table document
    legal_markers = sum(1 for kw in legal_keywords if kw in text_lower)
    if legal_markers > 3:
        # High density of legal markers → skip table detection
        return False

    # POSITIVE indicators: Real tables
    table_keywords = [
        "таблиця",
        "таблица",
        "table",
        "┌",
        "└",
        "├",
        "┤",
        "│",
        "─",  # Box drawing chars
        "+---+",
        "+===+",  # ASCII table markers
    ]

    # Strong table indicators
    has_table_keywords = any(kw in text_lower for kw in table_keywords)

    if has_table_keywords:
        return True

    # Check for aligned columns (but only if NOT legal document)
    # Real tables: many short aligned lines
    # Legal docs: few aligned lines (section headers)
    lines = text.split("\n")
    aligned_lines = 0
    short_aligned_lines = 0  # Lines < 80 chars

    for i in range(len(lines) - 2):
        len1, len2, len3 = len(lines[i]), len(lines[i + 1]), len(lines[i + 2])

        # Similar length lines
        if abs(len1 - len2) < 10 and abs(len2 - len3) < 10 and 20 < len1 < 150:
            aligned_lines += 1

            # Short lines more likely tables
            if len1 < 80:
                short_aligned_lines += 1

    # Real tables typically have many short aligned lines
    # Legal docs have few long aligned sections
    return short_aligned_lines > 5 and aligned_lines > 10


def detect_pdf_complexity(pdf_path: str) -> dict:
    """
    Fast PDF complexity detection to decide: Docling vs PyMuPDF.

    Target: < 500ms detection time

    Args:
        pdf_path: Path to PDF file

    Returns:
        {
            "use_docling": bool,
            "reason": str,
            "confidence": float,
            "metrics": {
                "detection_time_ms": float,
                "has_text_layer": bool,
                "image_count": int,
                "table_detected": bool,
                "sample_pages_checked": int
            }
        }
    """
    start_time = time.time()

    try:
        doc = fitz.open(pdf_path)

        # Check up to 3 pages for fast detection
        pages_to_check = min(3, len(doc))

        # Check 1: Text layer presence
        sample_text = ""
        for page_num in range(pages_to_check):
            sample_text += doc[page_num].get_text("text")

        has_text_layer = len(sample_text.strip()) > 100

        # Check 2: Image count (scans, photos)
        image_count = 0
        for page_num in range(pages_to_check):
            image_count += len(doc[page_num].get_images())

        has_images = image_count > 5

        # Check 3: Table detection (heuristic)
        table_detected = detect_tables_heuristic(sample_text[:5000])

        doc.close()

        # Decision logic
        if not has_text_layer:
            decision = True
            reason = "OCR required (no text layer detected)"
            confidence = 0.95
        elif has_images:
            decision = True
            reason = f"Contains {image_count} images/scans (might need OCR)"
            confidence = 0.85
        elif table_detected:
            decision = True
            reason = "Complex tables detected (TableFormer recommended)"
            confidence = 0.75
        else:
            decision = False
            reason = "Simple text document → PyMuPDF fast path"
            confidence = 0.90

        detection_time_ms = (time.time() - start_time) * 1000

        return {
            "use_docling": decision,
            "reason": reason,
            "confidence": confidence,
            "metrics": {
                "detection_time_ms": detection_time_ms,
                "has_text_layer": has_text_layer,
                "image_count": image_count,
                "table_detected": table_detected,
                "sample_pages_checked": pages_to_check,
            },
        }

    except Exception as e:
        # On error, default to Docling (safer)
        return {
            "use_docling": True,
            "reason": f"Detection error: {e} - defaulting to Docling",
            "confidence": 0.5,
            "metrics": {
                "detection_time_ms": (time.time() - start_time) * 1000,
                "has_text_layer": None,
                "image_count": None,
                "table_detected": None,
                "sample_pages_checked": 0,
            },
        }


def docling_chunk(pdf_path: str, max_retries: int = 3) -> dict:
    """
    Chunk document with SMART DETECTION: Docling vs PyMuPDF.

    PHASE 1.1: Smart Detection Logic
    - Fast complexity analysis (< 500ms) for PDF
    - Skip Docling for simple text PDFs
    - Use Docling only when needed (OCR, tables, images)
    - For DOCX: always use Docling API (no complexity check)

    Args:
        pdf_path: Path to PDF or DOCX file
        max_retries: Number of retry attempts (default: 3)

    Returns:
        Docling response with chunks (or PyMuPDF fallback)
    """
    import os
    from pathlib import Path

    file_ext = Path(pdf_path).suffix.lower()
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)

    print(f"  ℹ️  File: {Path(pdf_path).name}")
    print(f"  ℹ️  Format: {file_ext.upper()}")
    print(f"  ℹ️  Size: {file_size_mb:.1f} MB")

    # For DOCX files, detect if it's a legal document
    if file_ext == ".docx":
        print("  ✅ DOCX format detected → Checking document type...")

        # Check if it's a Ukrainian legal document (has "Стаття" pattern)
        try:
            import fitz

            doc = fitz.open(pdf_path)
            sample_text = ""
            for page_num in range(min(5, len(doc))):
                sample_text += doc[page_num].get_text("text")
            doc.close()

            # Check for Ukrainian legal markers
            has_articles = "Стаття" in sample_text or "статт" in sample_text.lower()
            is_legal = (
                has_articles
                and ("Кодекс" in sample_text or "Закон" in sample_text)
                and len(sample_text) > 1000
            )

            if is_legal:
                print("  ✓ Legal document detected (has 'Стаття' markers) → PyMuPDF fast path")
                detection = {
                    "use_docling": False,
                    "reason": "Ukrainian legal DOCX → PyMuPDF for better structure detection",
                    "confidence": 0.95,
                    "metrics": {
                        "detection_time_ms": 0,
                        "has_text_layer": True,
                        "image_count": 0,
                        "table_detected": False,
                        "sample_pages_checked": min(5, len(doc)) if "doc" in locals() else 0,
                    },
                }
            else:
                print("  ✓ Generic DOCX document → Using Docling API")
                detection = {
                    "use_docling": True,
                    "reason": "Generic DOCX format requires Docling API",
                    "confidence": 1.0,
                    "metrics": {
                        "detection_time_ms": 0,
                        "has_text_layer": True,
                        "image_count": None,
                        "table_detected": None,
                        "sample_pages_checked": 0,
                    },
                }

        except Exception as e:
            print(f"  ⚠️  Could not analyze DOCX: {e}")
            print("  ✓ Defaulting to Docling API")
            detection = {
                "use_docling": True,
                "reason": "DOCX analysis failed → default to Docling",
                "confidence": 0.5,
                "metrics": {
                    "detection_time_ms": 0,
                    "has_text_layer": None,
                    "image_count": None,
                    "table_detected": None,
                    "sample_pages_checked": 0,
                },
            }
    else:
        # PHASE 1.1: Smart Detection for PDF
        print("  🔍 Running complexity detection...")
        detection = detect_pdf_complexity(pdf_path)

        print(f"  ✓ Detection completed in {detection['metrics']['detection_time_ms']:.0f}ms")
        print(f"  ✓ Decision: {'Docling' if detection['use_docling'] else 'PyMuPDF fast path'}")
        print(f"  ✓ Reason: {detection['reason']}")
        print(f"  ✓ Confidence: {detection['confidence']:.0%}")

    # If simple text document → skip Docling entirely!
    if not detection["use_docling"]:
        print("  ⚡ Skipping Docling (unnecessary for simple text) → PyMuPDF")

        try:
            from pymupdf_chunker import PyMuPDFChunker

            start_time = time.time()
            chunker = PyMuPDFChunker(
                target_chunk_size=600, min_chunk_size=400, max_chunk_size=800, overlap_percent=0.12
            )
            chunks = chunker.chunk_pdf(pdf_path)
            processing_time = time.time() - start_time

            print(f"  ✓ PyMuPDF completed: {len(chunks)} chunks in {processing_time:.2f}s")

            return {
                "chunks": chunks,
                "processing_time": processing_time,
                "chunker": "pymupdf_fast_path",
                "detection": detection,
                "docling_skipped": True,
            }

        except Exception as e:
            print(f"  ⚠️  PyMuPDF fast path failed: {e}")
            print("  🔄 Falling back to Docling...")
            # Continue to Docling below

    # Docling path (for complex PDFs or if PyMuPDF failed)
    # Adaptive timeout based on file size
    # Rule: ~1 minute per 1 MB + 2 min base
    timeout = max(DOCLING_TIMEOUT, int(120 + file_size_mb * 60))
    print(f"  ℹ️  Docling timeout: {timeout}s (~{timeout // 60} minutes)")

    for attempt in range(max_retries):
        try:
            with open(pdf_path, "rb") as f:
                print(f"  ⏳ Sending to Docling (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(
                    f"{DOCLING_URL}/v1/chunk/hybrid/file", files={"files": f}, timeout=timeout
                )
            response.raise_for_status()
            print("  ✓ Docling chunking completed!")
            return response.json()

        except (requests.exceptions.ReadTimeout, requests.exceptions.HTTPError) as e:
            if attempt == max_retries - 1:
                # All Docling attempts failed → Use PyMuPDF fallback
                print(f"\n  ⚠️  Docling failed after {max_retries} attempts: {e}")
                print("  🔄 Falling back to PyMuPDF chunker (no ML, regex-based)...")

                try:
                    from pymupdf_chunker import PyMuPDFChunker

                    start_time = time.time()
                    chunker = PyMuPDFChunker(
                        target_chunk_size=600,
                        min_chunk_size=400,
                        max_chunk_size=800,
                        overlap_percent=0.12,
                    )
                    chunks = chunker.chunk_pdf(pdf_path)
                    processing_time = time.time() - start_time

                    print(
                        f"  ✓ PyMuPDF fallback completed: {len(chunks)} chunks in {processing_time:.2f}s"
                    )

                    # Convert to Docling-compatible format
                    return {
                        "chunks": chunks,
                        "processing_time": processing_time,
                        "chunker": "pymupdf_fallback",
                        "fallback_reason": str(e),
                    }

                except Exception as fallback_error:
                    raise Exception(
                        f"Both Docling and PyMuPDF fallback failed. "
                        f"Docling: {e}, PyMuPDF: {fallback_error}"
                    )
            else:
                wait_time = 30 * (attempt + 1)
                print(f"  ⚠️  Timeout on attempt {attempt + 1}, retrying in {wait_time}s...")
                time.sleep(wait_time)

        except Exception as e:
            if attempt == max_retries - 1:
                # Try PyMuPDF fallback for any other error
                print(f"\n  ⚠️  Docling error after {max_retries} attempts: {e}")
                print("  🔄 Falling back to PyMuPDF chunker...")

                try:
                    from pymupdf_chunker import PyMuPDFChunker

                    start_time = time.time()
                    chunker = PyMuPDFChunker()
                    chunks = chunker.chunk_pdf(pdf_path)
                    processing_time = time.time() - start_time

                    print(
                        f"  ✓ PyMuPDF fallback completed: {len(chunks)} chunks in {processing_time:.2f}s"
                    )

                    return {
                        "chunks": chunks,
                        "processing_time": processing_time,
                        "chunker": "pymupdf_fallback",
                        "fallback_reason": str(e),
                    }

                except Exception as fallback_error:
                    raise Exception(
                        f"Both Docling and PyMuPDF failed. Docling: {e}, PyMuPDF: {fallback_error}"
                    )
            else:
                wait_time = 10 * (attempt + 1)
                print(f"  ⚠️  Error on attempt {attempt + 1}: {e}")
                print(f"  Retrying in {wait_time}s...")
                time.sleep(wait_time)
    return None


def bge_m3_encode(text: str) -> dict:
    """Encode text with BGE-M3."""
    response = requests.post(
        f"{BGE_M3_URL}/encode/hybrid", json={"texts": [text]}, timeout=BGE_M3_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def generate_chunk_id(chunk_text: str, source: str, chunk_index: int) -> str:
    """
    Generate stable UUID for chunk based on content hash.

    This enables automatic deduplication:
    - Same content = same ID = Qdrant upsert updates existing point
    - Different content = different ID = new point created

    Args:
        chunk_text: Text content of the chunk
        source: Source document path
        chunk_index: Index within document (for tie-breaking)

    Returns:
        UUID string (Qdrant supports string IDs)
    """
    # Include source + content for hash (allows cross-document dedup)
    content = f"{source}::{chunk_text}"
    hash_obj = hashlib.sha256(content.encode("utf-8"))

    # Use first 32 hex chars as UUID
    # This gives us 2^128 possible IDs (collision probability ~0)
    return hash_obj.hexdigest()[:32]


def qdrant_upsert(collection: str, point_id: str, vectors: dict, payload: dict):
    """
    Insert or update point in Qdrant.

    Upsert means:
    - If point_id exists → update
    - If point_id doesn't exist → create

    This enables automatic deduplication when using content-based IDs.
    """
    data = {"points": [{"id": point_id, "vector": vectors, "payload": payload}]}

    response = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        json=data,
        headers={"api-key": QDRANT_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


async def process_chunk_async(
    contextualizer: ContextualRetrievalZAIAsync,
    chunk_data: dict,
    collection_name: str,
    document_name: str,
    pdf_path: str,
    chunk_index: int,
) -> dict:
    """
    Process single chunk asynchronously with content-based deduplication.

    Args:
        contextualizer: Z.AI async contextualizer
        chunk_data: Full chunk dict from chunker (includes text + metadata)
        collection_name: Qdrant collection
        document_name: Name of document
        pdf_path: Source PDF path
        chunk_index: Index within document

    Returns:
        Dict with status and chunk_id
    """
    try:
        chunk_text = chunk_data["text"]

        # Generate stable UUID from content hash (enables auto-deduplication)
        chunk_id = generate_chunk_id(chunk_text, pdf_path, chunk_index)

        # Generate context + metadata (ASYNC, NO document context!)
        context_text, metadata = await contextualizer.situate_context_with_metadata(
            chunk_text=chunk_text, document_name=document_name
        )

        # IMPORTANT: Preserve metadata from chunker (article_number, etc.)
        # Chunker metadata has priority over contextualizer metadata
        for key in [
            "article_number",
            "article_title",
            "chapter",
            "chapter_number",
            "section",
            "section_number",
            "book",
            "book_number",
        ]:
            if key in chunk_data and chunk_data[key] is not None:
                metadata[key] = chunk_data[key]

        # Add graph edges
        metadata = add_graph_edges(metadata)

        # Prepare contextualized text
        embedded_text = f"{context_text}\n\n{chunk_text}"

        # Embed with BGE-M3 (sync call, but fast ~100ms)
        embeddings = bge_m3_encode(embedded_text)

        # Prepare payload
        payload = {
            "text": chunk_text,
            "chunk_id": chunk_id,  # Store hash for reference/debugging
            "contextual_prefix": context_text,
            "embedded_text": embedded_text,
            "document": document_name,
            **metadata,
            "source": pdf_path,
            "chunk_index": chunk_index,
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

        # Insert into Qdrant (sync call)
        qdrant_upsert(collection_name, chunk_id, vectors, payload)

        return {"status": "success", "chunk_id": chunk_id}

    except Exception as e:
        # chunk_id might not be defined if error happens early
        error_id = chunk_id if "chunk_id" in locals() else f"index_{chunk_index}"
        return {"status": "failed", "chunk_id": error_id, "error": str(e)}


async def process_document_contextual_kg_async(
    pdf_path: str,
    collection_name: str,
    max_chunks: int | None = None,
    document_name: str = DOCUMENT_NAME,
    max_concurrent: int = 10,
    enable_mlflow: bool = True,
):
    """
    FAST async ingestion pipeline with MLflow tracking.

    Args:
        pdf_path: Path to PDF
        collection_name: Qdrant collection
        max_chunks: Limit for testing
        document_name: Document name
        max_concurrent: Max parallel requests (10 recommended)
        enable_mlflow: Enable MLflow experiment tracking (default: True)
    """
    print_header("⚡ FAST CONTEXTUAL RETRIEVAL + KG INGESTION")
    print_info(f"Document: {document_name}", 0)
    print_info(f"PDF Path: {pdf_path}", 0)
    print_info(f"Collection: {collection_name}", 0)
    print_info(f"Max chunks: {max_chunks or 'ALL'}", 0)
    print_info(f"Concurrency: {max_concurrent} parallel requests", 0)
    if enable_mlflow:
        print_info("📊 MLflow: ENABLED (tracking experiment)", 0)

    start_time = time.time()

    # Initialize MLflow if enabled
    mlflow_logger = None
    mlflow_run = None
    if enable_mlflow:
        try:
            mlflow_logger = MLflowRAGLogger(experiment_name="contextual_rag_ingestion")
            doc_short_name = Path(pdf_path).stem[:30]  # Truncate for run name
            run_name = f"ingestion_{doc_short_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            mlflow_run = mlflow_logger.start_run(
                run_name=run_name, tags={"document": document_name, "collection": collection_name}
            )
            mlflow_run.__enter__()  # Enter context manager
            print_info(f"📊 MLflow run: {run_name}", 0)
        except Exception as e:
            print(f"\n⚠️  WARNING: MLflow init failed: {e}")
            print("   Continuing without MLflow tracking...")
            enable_mlflow = False

    # Initialize async contextualizer
    print_step(0, "INITIALIZATION")
    try:
        contextualizer = ContextualRetrievalZAIAsync(
            api_key=ZAI_API_KEY,
            rate_limit_delay=0.5,  # Reduced delay
            max_concurrent=max_concurrent,
        )
        print_info("ContextualRetrievalZAIAsync initialized")
        print_info("OPTIMIZATION: NO document context (saves ~8,750 tokens/request)")
        print_info("OPTIMIZATION: Async parallel processing")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to initialize: {e}")
        return False

    # Chunking (Smart Detection → Docling or PyMuPDF)
    print_step(1, "DOCUMENT CHUNKING")
    try:
        doc_data = docling_chunk(pdf_path)
        chunks = doc_data["chunks"]
        chunker_used = doc_data.get("chunker", "docling")

        print_info(f"Chunker: {chunker_used}")
        print_info(f"Total chunks: {len(chunks)}")
        print_info(f"Processing time: {doc_data['processing_time']:.2f}s")

        # Show detection metrics if available
        if "detection" in doc_data:
            detection = doc_data["detection"]
            print_info(f"Detection time: {detection['metrics']['detection_time_ms']:.0f}ms")
            print_info(f"Detection confidence: {detection['confidence']:.0%}")

        # Show if Docling was skipped (fast path)
        if doc_data.get("docling_skipped"):
            print_info("✨ OPTIMIZATION: Docling skipped (simple text PDF)")
            print_info(f"   Time saved: ~{DOCLING_TIMEOUT}s (no unnecessary retries)")

        # Show fallback reason if applicable
        if chunker_used == "pymupdf_fallback":
            print_info(f"Fallback reason: {doc_data.get('fallback_reason', 'Unknown')}")

        if max_chunks:
            chunks = chunks[:max_chunks]
            print_info(f"Limited to {max_chunks} chunks for testing")

        # Log config to MLflow
        if enable_mlflow and mlflow_logger:
            mlflow_logger.log_config(
                {
                    "pdf_path": pdf_path,
                    "document_name": document_name,
                    "collection_name": collection_name,
                    "chunker_used": chunker_used,
                    "total_chunks": len(chunks),
                    "max_chunks": max_chunks or "ALL",
                    "max_concurrent": max_concurrent,
                    "enable_contextualization": True,
                    "llm_model": "glm-4.6",
                    "embedding_model": "bge-m3",
                    "docling_skipped": doc_data.get("docling_skipped", False),
                },
                prefix="ingestion.",
            )

    except Exception as e:
        print(f"\n❌ ERROR: Chunking failed: {e}")
        if enable_mlflow and mlflow_run:
            mlflow_run.__exit__(None, None, None)
        return False

    # Process chunks in parallel
    print_step(2, "ASYNC CONTEXTUAL EMBEDDING + KG")
    print()

    stats = {"total": len(chunks), "success": 0, "failed": 0, "start": time.time()}

    # Create async tasks
    tasks = []
    for idx, chunk in enumerate(chunks):
        task = process_chunk_async(
            contextualizer=contextualizer,
            chunk_data=chunk,  # Pass full chunk dict with metadata
            collection_name=collection_name,
            document_name=document_name,
            pdf_path=pdf_path,
            chunk_index=idx,
        )
        tasks.append(task)

    # Process with progress tracking
    completed = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        completed += 1

        if result["status"] == "success":
            stats["success"] += 1
        else:
            stats["failed"] += 1
            print(f"\n  ✗ Chunk {result['chunk_id']} failed: {result.get('error', 'Unknown')}")

        print_progress(completed, len(chunks), "Processing...")

    print()  # New line after progress
    stats["elapsed"] = time.time() - stats["start"]

    # Print statistics
    print("\n  📊 Processing Statistics:")
    print_info(f"Total chunks: {stats['total']}", 2)
    print_info(f"Success: {stats['success']}", 2)
    print_info(f"Failed: {stats['failed']}", 2)
    print_info(f"Total time: {stats['elapsed']:.2f}s", 2)
    print_info(f"Avg per chunk: {stats['elapsed'] / stats['total']:.2f}s", 2)

    # Speedup calculation
    old_time_per_chunk = 8.21  # From original test
    old_estimated = old_time_per_chunk * stats["total"]
    speedup = old_estimated / stats["elapsed"]
    print_info(
        f"SPEEDUP: {speedup:.1f}x faster ({old_estimated:.0f}s → {stats['elapsed']:.0f}s)", 2
    )

    # Print contextualizer stats
    contextualizer.print_stats()

    # Verify collection
    print_step(3, "VERIFICATION")
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
    print_info(f"SPEEDUP: {speedup:.1f}x faster than original", 0)

    # Log metrics to MLflow
    if enable_mlflow and mlflow_logger:
        # Calculate metadata coverage
        sample_chunks_for_coverage = chunks[: min(100, len(chunks))]  # Sample first 100
        chunks_with_metadata = sum(1 for c in sample_chunks_for_coverage if c.get("article_number"))
        metadata_coverage = chunks_with_metadata / len(sample_chunks_for_coverage)

        # Calculate avg chunk size
        avg_chunk_size = np.mean([len(c["text"]) for c in chunks])

        mlflow_logger.log_metrics(
            {
                "chunks_created": len(chunks),
                "chunks_success": stats["success"],
                "chunks_failed": stats["failed"],
                "ingestion_time_seconds": total_time,
                "processing_time_seconds": stats["elapsed"],
                "avg_chunk_size_chars": float(avg_chunk_size),
                "avg_time_per_chunk_seconds": stats["elapsed"] / stats["total"],
                "speedup_factor": float(speedup),
                "metadata_coverage_percent": metadata_coverage * 100,
            }
        )

        # Log sample chunks as artifact
        sample_chunks = chunks[:5]  # First 5 chunks
        mlflow_logger.log_dict_artifact(
            {
                "chunks": [
                    {"text": c["text"][:200], **{k: v for k, v in c.items() if k != "text"}}
                    for c in sample_chunks
                ]
            },
            "chunk_samples.json",
            artifact_path="samples",
        )

        # Close MLflow run
        try:
            if mlflow_run:
                run_url = mlflow_logger.get_run_url()
                print_info(f"📊 MLflow run: {run_url}", 0)
                mlflow_run.__exit__(None, None, None)
        except Exception as e:
            print(f"\n⚠️  WARNING: Error closing MLflow run: {e}")

    print("=" * 80)

    return stats["failed"] == 0


# Async wrapper
async def main_async(args):
    """Async main entry point."""
    # Determine max chunks
    max_chunks = TEST_MAX_CHUNKS if args.test else args.max_chunks

    # Create collection
    print_header("STEP 0: CREATE COLLECTION")
    from create_collection_enhanced import create_enhanced_collection

    try:
        create_enhanced_collection(args.collection)
    except Exception as e:
        print(f"❌ ERROR: Failed to create collection: {e}")
        return False

    # Run async ingestion
    return await process_document_contextual_kg_async(
        pdf_path=args.pdf,
        collection_name=args.collection,
        max_chunks=max_chunks,
        document_name=args.document_name,
        max_concurrent=args.concurrent,
    )


if __name__ == "__main__":
    import argparse
    import os.path

    parser = argparse.ArgumentParser(
        description="FAST Contextual RAG Ingestion - Universal PDF Processor",
        epilog="Examples:\n"
        "  python3 %(prog)s /path/to/document.pdf\n"
        "  python3 %(prog)s --pdf /path/to/document.pdf --collection my_collection\n"
        "  python3 %(prog)s --pdf /path/to/document.pdf --test\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # PDF file path - supports both positional and --pdf flag
    parser.add_argument(
        "pdf_positional", nargs="?", default=None, help="Path to PDF file (positional, optional)"
    )
    parser.add_argument(
        "--pdf", dest="pdf_flag", default=None, help="Path to PDF file (explicit flag)"
    )

    # Optional arguments
    parser.add_argument("--test", action="store_true", help="Test mode (5 chunks only)")
    parser.add_argument("--max-chunks", type=int, help="Max chunks to process")
    parser.add_argument(
        "--collection", help="Collection name (auto-generated from filename if not specified)"
    )
    parser.add_argument(
        "--document-name",
        help="Document name for context (auto-extracted from filename if not specified)",
    )
    parser.add_argument(
        "--concurrent", type=int, default=10, help="Max concurrent requests (default: 10)"
    )

    args = parser.parse_args()

    # Determine PDF path: --pdf flag takes priority, then positional, then default
    if args.pdf_flag:
        args.pdf = args.pdf_flag
    elif args.pdf_positional:
        args.pdf = args.pdf_positional
    else:
        args.pdf = PDF_PATH

    # Auto-generate collection name from PDF filename if not specified
    if not args.collection:
        pdf_basename = os.path.basename(args.pdf)
        # Remove extension and convert to lowercase with underscores
        collection_base = os.path.splitext(pdf_basename)[0]
        collection_base = collection_base.lower().replace(" ", "_").replace("-", "_")
        args.collection = f"{collection_base}_contextual_kg"
        print(f"  ℹ️  Auto-generated collection name: {args.collection}")

    # Auto-extract document name if not specified
    if not args.document_name:
        pdf_basename = os.path.basename(args.pdf)
        # Extract readable name from filename
        doc_name = os.path.splitext(pdf_basename)[0]
        # Clean up: remove dates, "as_of", etc.
        doc_name = doc_name.replace("_", " ").replace("-", " ")
        doc_name = doc_name.replace(" as of ", " ").replace(" RU", "")
        args.document_name = doc_name
        print(f"  ℹ️  Auto-extracted document name: {args.document_name}")

    # Validate PDF file exists
    if not os.path.exists(args.pdf):
        print(f"❌ ERROR: PDF file not found: {args.pdf}")
        sys.exit(1)

    # Check API keys
    if not ZAI_API_KEY:
        print("⚠️  WARNING: ZAI_API_KEY not set - will use fallback regex parser")

    print(f"✅ PDF file found: {args.pdf}")
    print(f"✅ Collection: {args.collection}")
    print(f"✅ Document: {args.document_name}")

    # Run async main
    success = asyncio.run(main_async(args))

    sys.exit(0 if success else 1)
