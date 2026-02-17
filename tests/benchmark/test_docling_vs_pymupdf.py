#!/usr/bin/env python3
"""
Comparison test: Docling HybridChunker vs PyMuPDF chunker
Tests both approaches on the same Ukrainian legal document.
"""

import sys
from pathlib import Path

import pytest


# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "legacy"))

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

from legacy.pymupdf_chunker import PyMuPDFChunker


def _run_pymupdf_approach():
    """Run PyMuPDF regex-based chunking flow."""
    print("=" * 80)
    print("🔧 APPROACH 1: PyMuPDF (Regex-based)")
    print("=" * 80)

    docx_path = "docs/documents/Кримінальний кодекс України - Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx"

    if not Path(docx_path).exists():
        print(f"❌ File not found: {docx_path}")
        return None

    print("\n⚙️  Creating PyMuPDFChunker...")
    chunker = PyMuPDFChunker(target_chunk_size=600, min_chunk_size=400, max_chunk_size=800)

    print("⚙️  Chunking document...")
    chunks = chunker.chunk_pdf(docx_path)

    print(f"✅ Created {len(chunks)} chunks\n")

    # Analyze metadata
    chunks_with_article = [c for c in chunks if c.get("article_number") is not None]
    coverage = len(chunks_with_article) / len(chunks) * 100

    print("📊 Metadata Analysis:")
    print(f"   Total chunks: {len(chunks)}")
    print(f"   With article_number: {len(chunks_with_article)} ({coverage:.1f}%)")
    print(f"   Without article_number: {len(chunks) - len(chunks_with_article)}")

    # Show sample
    print("\n📄 Sample chunk (first with article):")
    sample = chunks_with_article[0]
    print(f"   article_number: {sample.get('article_number')}")
    print(f"   article_title: {sample.get('article_title', 'N/A')}")
    print(f"   text: {sample['text'][:150]}...")

    return chunks


def _run_docling_approach():
    """Run Docling HybridChunker flow."""
    print("\n" + "=" * 80)
    print("🔧 APPROACH 2: Docling HybridChunker (Structure-aware)")
    print("=" * 80)

    docx_path = "docs/documents/Кримінальний кодекс України - Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx"

    if not Path(docx_path).exists():
        print(f"❌ File not found: {docx_path}")
        return None

    print("\n⚙️  Creating DocumentConverter...")
    converter = DocumentConverter()

    print("⚙️  Converting document to DoclingDocument...")
    result = converter.convert(docx_path)
    doc = result.document

    print(f"✅ Document converted: {doc.name}")
    print(f"   Pages: {len(doc.pages)}")
    print(f"   Main text items: {len(doc.texts)}")

    # Initialize tokenizer (same as for embeddings)
    print("\n⚙️  Creating HybridChunker with HuggingFace tokenizer...")
    EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(EMBED_MODEL_ID),
        max_tokens=800,  # Match PyMuPDF max
    )

    chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)

    print("⚙️  Chunking document...")
    chunks = list(chunker.chunk(dl_doc=doc))

    print(f"✅ Created {len(chunks)} chunks\n")

    # Analyze metadata - Docling chunks have different structure
    print("📊 Metadata Analysis:")
    print(f"   Total chunks: {len(chunks)}")

    # Docling chunks have meta.headings instead of article_number
    chunks_with_headings = [c for c in chunks if c.meta.headings]
    print(
        f"   With headings: {len(chunks_with_headings)} ({len(chunks_with_headings) / len(chunks) * 100:.1f}%)"
    )

    # Show sample
    print("\n📄 Sample chunk (first with headings):")
    if chunks_with_headings:
        sample = chunks_with_headings[0]
        print(f"   headings: {sample.meta.headings}")
        print(f"   doc_items: {len(sample.meta.doc_items)} items")
        print(f"   text: {sample.text[:150]}...")
    else:
        print("   ⚠️  No chunks with headings found!")

    # Try to find article numbers in text
    chunks_with_article_in_text = []
    for chunk in chunks:
        if "Стаття" in chunk.text[:50]:  # Check if starts with "Стаття"
            chunks_with_article_in_text.append(chunk)

    print(f"\n   Chunks starting with 'Стаття': {len(chunks_with_article_in_text)}")

    return chunks


def test_pymupdf_approach():
    """Test PyMuPDF regex-based chunking."""
    chunks = _run_pymupdf_approach()
    if chunks is None:
        pytest.skip("Source DOCX file not found for benchmark test")
    assert chunks


def test_docling_approach():
    """Test Docling HybridChunker with document structure."""
    chunks = _run_docling_approach()
    if chunks is None:
        pytest.skip("Source DOCX file not found for benchmark test")
    assert chunks


def compare_approaches():
    """Compare both approaches side by side."""
    print("\n\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "DOCLING vs PyMuPDF COMPARISON" + " " * 28 + "║")
    print("╚" + "═" * 78 + "╝")

    pymupdf_chunks = _run_pymupdf_approach()
    docling_chunks = _run_docling_approach()

    if pymupdf_chunks and docling_chunks:
        print("\n\n" + "=" * 80)
        print("📊 COMPARISON SUMMARY")
        print("=" * 80)

        print(f"\n{'Metric':<40} {'PyMuPDF':<20} {'Docling':<20}")
        print("-" * 80)
        print(f"{'Total chunks':<40} {len(pymupdf_chunks):<20} {len(docling_chunks):<20}")

        # PyMuPDF metadata
        pymupdf_with_article = [c for c in pymupdf_chunks if c.get("article_number")]
        pymupdf_coverage = len(pymupdf_with_article) / len(pymupdf_chunks) * 100

        # Docling metadata
        docling_with_headings = [c for c in docling_chunks if c.meta.headings]
        docling_coverage = len(docling_with_headings) / len(docling_chunks) * 100

        print(f"{'Metadata coverage':<40} {pymupdf_coverage:.1f}%{'':<16} {docling_coverage:.1f}%")

        print(f"\n{'Metadata type':<40} {'article_number (int)':<20} {'headings (list)':<20}")

        print("\n" + "=" * 80)
        print("🔍 KEY OBSERVATIONS:")
        print("=" * 80)

        if pymupdf_coverage > docling_coverage:
            print("✅ PyMuPDF has better metadata coverage for Ukrainian legal docs")
            print("   → Reason: Regex patterns specifically target 'Стаття N' structure")
        else:
            print("✅ Docling has better metadata coverage")
            print("   → Reason: Structure-aware parsing detects document hierarchy")

        if len(pymupdf_chunks) < len(docling_chunks):
            print(
                f"✅ PyMuPDF creates fewer chunks ({len(pymupdf_chunks)} vs {len(docling_chunks)})"
            )
            print("   → Reason: Article-based chunking respects legal document structure")
        else:
            print(
                f"✅ Docling creates fewer chunks ({len(docling_chunks)} vs {len(pymupdf_chunks)})"
            )
            print("   → Reason: Hybrid chunking merges peers and respects hierarchy")

        print("\n💡 RECOMMENDATION:")
        if pymupdf_coverage == 100.0 and pymupdf_coverage > docling_coverage:
            print("   → Use PyMuPDF for Ukrainian legal documents (perfect metadata)")
        elif docling_coverage > pymupdf_coverage:
            print("   → Use Docling for generic documents (better structure detection)")
        else:
            print("   → Current approach (smart detection) is optimal")

        return True

    return False


if __name__ == "__main__":
    success = compare_approaches()
    sys.exit(0 if success else 1)
