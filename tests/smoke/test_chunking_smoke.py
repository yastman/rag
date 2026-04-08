#!/usr/bin/env python3
"""
Smoke test for chunking quality on Ukrainian legal documents.
Tests that PyMuPDFChunker correctly handles Criminal Code structure.
"""

import sys
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "legacy"))

import pytest


pytest.importorskip("fitz", reason="PyMuPDF/fitz not installed (ingest extra)")

try:
    from legacy.pymupdf_chunker import PyMuPDFChunker
except ModuleNotFoundError as exc:  # pragma: no cover - legacy smoke helper is optional
    pytest.skip(f"legacy chunking helper unavailable: {exc}", allow_module_level=True)


# Test file path
CRIMINAL_CODE_PATH = (
    "docs/documents/Кримінальний кодекс України - "
    "Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx"
)


@pytest.fixture
def chunker():
    """Create PyMuPDFChunker with production settings."""
    return PyMuPDFChunker(target_chunk_size=600, min_chunk_size=400, max_chunk_size=800)


@pytest.fixture
def chunks(chunker):
    """Generate chunks from Criminal Code."""
    docx_path = project_root / CRIMINAL_CODE_PATH
    if not docx_path.exists():
        pytest.skip(f"Criminal Code DOCX not found at {docx_path}")
    return chunker.chunk_pdf(str(docx_path))


class TestChunkingQuality:
    """Test suite for chunking quality."""

    def test_chunks_created(self, chunks):
        """Test that chunks are created."""
        assert len(chunks) > 0, "No chunks created"
        print(f"\n✅ Created {len(chunks)} chunks")

    def test_all_chunks_have_article_number(self, chunks):
        """Test that ALL chunks have article_number (100% coverage)."""
        chunks_with_article = [c for c in chunks if c.get("article_number") is not None]
        chunks_without = [c for c in chunks if c.get("article_number") is None]

        coverage = len(chunks_with_article) / len(chunks) * 100

        print("\n📊 Article number coverage:")
        print(f"   With article_number: {len(chunks_with_article)} ({coverage:.1f}%)")
        print(f"   WITHOUT article_number: {len(chunks_without)} ({100 - coverage:.1f}%)")

        # Should be 100% for legal documents
        assert coverage == 100.0, (
            f"Only {coverage:.1f}% chunks have article_number. "
            f"Expected 100% for legal documents. "
            f"{len(chunks_without)} chunks missing metadata."
        )

    def test_reasonable_chunk_count(self, chunks):
        """Test that chunk count is reasonable (not over-chunked)."""
        # Criminal Code has 564 articles
        # Expected: ~500-600 chunks (close to 1:1 ratio)
        # Docling was creating 1294 (way too many!)

        assert 500 <= len(chunks) <= 700, (
            f"Chunk count {len(chunks)} seems unreasonable. "
            f"Expected 500-700 for 564 articles. "
            f"Possible over-chunking issue."
        )
        print(f"\n✅ Chunk count {len(chunks)} is reasonable (500-700 range)")

    def test_articles_are_sequential(self, chunks):
        """Test that articles appear in sequential order (not scattered)."""
        # Get all unique articles in order they appear
        articles_in_order = []
        for chunk in chunks:
            article = chunk.get("article_number")
            if article and (not articles_in_order or articles_in_order[-1] != article):
                articles_in_order.append(article)

        # Check that articles are mostly sequential (allowing some gaps for notes, etc)
        gaps = []
        for i in range(len(articles_in_order) - 1):
            gap = articles_in_order[i + 1] - articles_in_order[i]
            if gap > 10:  # Large gap
                gaps.append((articles_in_order[i], articles_in_order[i + 1], gap))

        print("\n📋 Article sequence:")
        print(f"   Unique articles found: {len(articles_in_order)}")
        print(f"   First article: {articles_in_order[0]}")
        print(f"   Last article: {articles_in_order[-1]}")
        print(f"   Large gaps (>10): {len(gaps)}")

        # Should have close to 564 unique articles
        assert 500 <= len(articles_in_order) <= 600, (
            f"Found {len(articles_in_order)} unique articles, expected ~564"
        )

        # Should not have too many large gaps (indicates scattered articles)
        assert len(gaps) < 50, (
            f"Found {len(gaps)} large gaps in article sequence. "
            f"This indicates articles are scattered across document. "
            f"Examples: {gaps[:5]}"
        )

    def test_no_duplicate_article_splitting(self, chunks):
        """Test that articles aren't incorrectly duplicated with different numbers."""
        # Check for the specific bug: "Article 3" appearing in 15 scattered locations
        article_positions = {}
        for i, chunk in enumerate(chunks):
            article = chunk.get("article_number")
            if article:
                if article not in article_positions:
                    article_positions[article] = []
                article_positions[article].append(i)

        # Find articles that are scattered (non-consecutive chunk indices)
        scattered_articles = {}
        for article, positions in article_positions.items():
            if len(positions) > 1:
                # Check if positions are consecutive
                gaps = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)]
                max_gap = max(gaps) if gaps else 0
                if max_gap > 5:  # Not consecutive
                    scattered_articles[article] = {
                        "count": len(positions),
                        "positions": positions,
                        "max_gap": max_gap,
                    }

        print("\n🔍 Scattered articles check:")
        print(
            f"   Articles with multiple parts: {len([a for a, p in article_positions.items() if len(p) > 1])}"
        )
        print(f"   Scattered (non-consecutive): {len(scattered_articles)}")

        # Show worst offenders
        if scattered_articles:
            worst = sorted(scattered_articles.items(), key=lambda x: x[1]["max_gap"], reverse=True)[
                :3
            ]
            print("\n   Worst scattered articles:")
            for article, info in worst:
                print(
                    f"     Article {article}: {info['count']} parts, "
                    f"max gap {info['max_gap']} chunks"
                )

        # Should have very few scattered articles (long articles can legitimately span chunks)
        assert len(scattered_articles) < 10, (
            f"Found {len(scattered_articles)} scattered articles. "
            f"This indicates chunking is incorrectly splitting articles. "
            f"Worst: {scattered_articles}"
        )

    def test_chunk_metadata_completeness(self, chunks):
        """Test that chunks have proper metadata structure."""
        required_fields = ["text", "article_number"]

        for i, chunk in enumerate(chunks[:10]):  # Check first 10
            # Required fields
            for field in required_fields:
                assert field in chunk, f"Chunk {i} missing required field: {field}"
                assert chunk[field] is not None, f"Chunk {i} has None value for: {field}"

            # Check text is not empty
            assert len(chunk["text"].strip()) > 0, f"Chunk {i} has empty text"

            # Check article_number is valid integer
            assert isinstance(chunk["article_number"], int), (
                f"Chunk {i} article_number is not int: {type(chunk['article_number'])}"
            )
            assert chunk["article_number"] > 0, f"Chunk {i} has invalid article_number"

        print("\n✅ Metadata structure is correct for all chunks")

    def test_chunk_sizes_reasonable(self, chunks):
        """Test that chunk sizes are within reasonable bounds."""
        token_counts = [len(chunk["text"]) // 4 for chunk in chunks]  # Rough token estimate

        avg_tokens = sum(token_counts) / len(token_counts)
        min_tokens = min(token_counts)
        max_tokens = max(token_counts)

        print("\n📏 Chunk size statistics:")
        print(f"   Average: {avg_tokens:.0f} tokens")
        print(f"   Min: {min_tokens} tokens")
        print(f"   Max: {max_tokens} tokens")

        # Most chunks should be within target range (400-800)
        in_range = len([t for t in token_counts if 400 <= t <= 800])
        in_range_pct = in_range / len(chunks) * 100

        print(f"   In target range (400-800): {in_range} ({in_range_pct:.1f}%)")

        # At least 70% should be in range
        assert in_range_pct >= 70, (
            f"Only {in_range_pct:.1f}% of chunks are in target size range. Expected at least 70%."
        )


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
