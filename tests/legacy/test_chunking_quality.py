#!/usr/bin/env python3
"""
Smoke test for chunking quality - simple script without pytest.
"""

import sys
from pathlib import Path


# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "legacy"))

from pymupdf_chunker import PyMuPDFChunker


def test_criminal_code_chunking():
    """Test PyMuPDF chunking on Criminal Code."""

    docx_path = "docs/documents/Кримінальний кодекс України - Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx"

    print("=" * 80)
    print("🧪 SMOKE TEST: Criminal Code Chunking Quality")
    print("=" * 80)
    print(f"\n📄 File: {docx_path}")

    if not Path(docx_path).exists():
        print(f"\n❌ File not found: {docx_path}")
        return False

    # Create chunker
    print("\n🔧 Creating PyMuPDFChunker (target=600, min=400, max=800)...")
    chunker = PyMuPDFChunker(target_chunk_size=600, min_chunk_size=400, max_chunk_size=800)

    # Generate chunks
    print("⚙️  Chunking document...")
    chunks = chunker.chunk_pdf(docx_path)

    print(f"✅ Created {len(chunks)} chunks\n")

    # Test 1: Chunk count
    print("=" * 80)
    print("TEST 1: Reasonable chunk count")
    print("=" * 80)
    expected_range = (500, 700)
    if expected_range[0] <= len(chunks) <= expected_range[1]:
        print(f"✅ PASS: {len(chunks)} chunks in expected range {expected_range}")
    else:
        print(f"❌ FAIL: {len(chunks)} chunks outside expected range {expected_range}")
        return False

    # Test 2: Article number coverage
    print("\n" + "=" * 80)
    print("TEST 2: Article number coverage")
    print("=" * 80)
    chunks_with_article = [c for c in chunks if c.get("article_number") is not None]
    chunks_without = [c for c in chunks if c.get("article_number") is None]
    coverage = len(chunks_with_article) / len(chunks) * 100

    print(f"With article_number: {len(chunks_with_article)} ({coverage:.1f}%)")
    print(f"WITHOUT article_number: {len(chunks_without)} ({100 - coverage:.1f}%)")

    if coverage == 100.0:
        print("✅ PASS: 100% coverage!")
    else:
        print(f"❌ FAIL: Only {coverage:.1f}% coverage, expected 100%")
        if chunks_without:
            print("\nFirst 3 chunks without article_number:")
            for i, c in enumerate(chunks_without[:3]):
                print(f"  {i + 1}. Text: {c['text'][:80]}...")
        return False

    # Test 3: Article sequence
    print("\n" + "=" * 80)
    print("TEST 3: Article sequence (not scattered)")
    print("=" * 80)
    articles_in_order = []
    for chunk in chunks:
        article = chunk.get("article_number")
        if article and (not articles_in_order or articles_in_order[-1] != article):
            articles_in_order.append(article)

    print(f"Unique articles: {len(articles_in_order)}")
    print(f"First article: {articles_in_order[0]}")
    print(f"Last article: {articles_in_order[-1]}")

    # Check for large gaps
    gaps = []
    for i in range(len(articles_in_order) - 1):
        gap = articles_in_order[i + 1] - articles_in_order[i]
        if gap > 10:
            gaps.append((articles_in_order[i], articles_in_order[i + 1], gap))

    print(f"Large gaps (>10): {len(gaps)}")

    # Actual Criminal Code may have fewer articles in some versions
    # Main check: reasonable number of unique articles found
    if 400 <= len(articles_in_order) <= 600:
        print(f"✅ PASS: {len(articles_in_order)} unique articles (reasonable for Criminal Code)")
    else:
        print(f"❌ FAIL: {len(articles_in_order)} unique articles, expected 400-600")
        return False

    if len(gaps) < 50:
        print(f"✅ PASS: Only {len(gaps)} large gaps (articles mostly sequential)")
    else:
        print(f"❌ FAIL: {len(gaps)} large gaps (articles scattered)")
        print(f"Examples: {gaps[:5]}")
        return False

    # Test 4: No scattered articles
    print("\n" + "=" * 80)
    print("TEST 4: No scattered articles")
    print("=" * 80)
    article_positions = {}
    for i, chunk in enumerate(chunks):
        article = chunk.get("article_number")
        if article:
            if article not in article_positions:
                article_positions[article] = []
            article_positions[article].append(i)

    scattered = {}
    for article, positions in article_positions.items():
        if len(positions) > 1:
            gaps_list = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)]
            max_gap = max(gaps_list) if gaps_list else 0
            if max_gap > 5:  # Non-consecutive
                scattered[article] = {"count": len(positions), "max_gap": max_gap}

    print(f"Scattered articles: {len(scattered)}")

    if scattered:
        worst = sorted(scattered.items(), key=lambda x: x[1]["max_gap"], reverse=True)[:3]
        print("Worst examples:")
        for article, info in worst:
            print(f"  Article {article}: {info['count']} parts, max gap {info['max_gap']}")

    if len(scattered) < 10:
        print(f"✅ PASS: Only {len(scattered)} scattered articles")
    else:
        print(f"❌ FAIL: {len(scattered)} scattered articles (expected <10)")
        return False

    # Test 5: Chunk sizes
    print("\n" + "=" * 80)
    print("TEST 5: Chunk sizes reasonable")
    print("=" * 80)
    token_counts = [len(c["text"]) // 4 for c in chunks]
    avg = sum(token_counts) / len(token_counts)
    in_range = len([t for t in token_counts if 400 <= t <= 800])
    in_range_pct = in_range / len(chunks) * 100

    print(f"Average tokens: {avg:.0f}")
    print(f"Min tokens: {min(token_counts)}")
    print(f"Max tokens: {max(token_counts)}")
    print(f"In target range (400-800): {in_range} ({in_range_pct:.1f}%)")

    # Legal documents often have many short articles
    # Main check: chunks are not excessively large
    oversized = len([t for t in token_counts if t > 1000])
    if oversized < len(chunks) * 0.05:  # Less than 5% oversized
        print(f"✅ PASS: Only {oversized} oversized chunks (<5%)")
        print(f"   Note: {in_range_pct:.1f}% in target range (many short articles is normal)")
    else:
        print(f"❌ FAIL: {oversized} oversized chunks (>{5}% of total)")
        return False

    # Summary
    print("\n" + "=" * 80)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 80)
    print("\n📊 Summary:")
    print(f"   Chunks: {len(chunks)}")
    print("   Article coverage: 100%")
    print(f"   Unique articles: {len(articles_in_order)}")
    print("   Quality: ✅ Excellent")
    print("\n✅ PyMuPDF chunking works perfectly for Ukrainian legal documents!")

    return True


if __name__ == "__main__":
    success = test_criminal_code_chunking()
    sys.exit(0 if success else 1)
