#!/usr/bin/env python3
"""
A/B Test: OpenAI vs Groq API Comparison
Tests contextualization quality, speed, and cost
"""

import asyncio
import json
import time

from dotenv import load_dotenv


# Load environment variables
load_dotenv()

from contextualize_groq_async import ContextualRetrievalGroqAsync
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
from pymupdf_chunker import PyMuPDFChunker


def load_test_chunks(pdf_path: str, num_chunks: int = 10) -> list[dict]:
    """Load test chunks from PDF."""
    print(f"📄 Loading {num_chunks} chunks from Criminal Code...")

    chunker = PyMuPDFChunker(
        target_chunk_size=600, min_chunk_size=400, max_chunk_size=800, overlap_percent=0.12
    )

    chunks = chunker.chunk_pdf(pdf_path)

    # Select diverse chunks (beginning, middle, end)
    if len(chunks) <= num_chunks:
        selected = chunks
    else:
        step = len(chunks) // num_chunks
        selected = [chunks[i * step] for i in range(num_chunks)]

    print(f"✓ Loaded {len(selected)} chunks")
    print(f"  Sample articles: {[c.get('article_number') for c in selected[:5]]}")

    return selected


async def test_openai(chunks: list[dict], model: str = "gpt-4o-mini") -> dict:
    """Test OpenAI API."""
    print(f"\n{'=' * 80}")
    print(f"🤖 Testing OpenAI ({model})...")
    print(f"{'=' * 80}")

    contextualizer = ContextualRetrievalOpenAIAsync(
        model=model,
        max_concurrent=5,  # Conservative limit
    )

    results = []
    start_time = time.time()

    for i, chunk in enumerate(chunks):
        chunk_text = chunk["text"]
        print(f"\n[{i + 1}/{len(chunks)}] Processing article {chunk.get('article_number', '?')}...")

        context_text, metadata = await contextualizer.situate_context_with_metadata(chunk_text)

        results.append(
            {
                "chunk_index": i,
                "article_number": chunk.get("article_number"),
                "context_text": context_text,
                "metadata": metadata,
                "chunk_text_preview": chunk_text[:200],
            }
        )

        print(f"  Context: {context_text[:100]}...")
        print(
            f"  Metadata: article={metadata.get('article_number')}, "
            f"book={metadata.get('book_number')}, "
            f"section={metadata.get('section_number')}"
        )

    total_time = time.time() - start_time

    # Get stats
    stats = contextualizer.get_stats()
    contextualizer.print_stats()

    return {
        "provider": "OpenAI",
        "model": model,
        "results": results,
        "stats": stats,
        "total_time": total_time,
        "avg_time_per_chunk": total_time / len(chunks),
    }


async def test_groq(chunks: list[dict], model: str = "llama-3.1-8b-instant") -> dict:
    """Test Groq API."""
    print(f"\n{'=' * 80}")
    print(f"⚡ Testing Groq ({model})...")
    print(f"{'=' * 80}")

    contextualizer = ContextualRetrievalGroqAsync(
        model=model,
        max_concurrent=10,  ***REMOVED*** can handle more
    )

    results = []
    start_time = time.time()

    for i, chunk in enumerate(chunks):
        chunk_text = chunk["text"]
        print(f"\n[{i + 1}/{len(chunks)}] Processing article {chunk.get('article_number', '?')}...")

        context_text, metadata = await contextualizer.situate_context_with_metadata(chunk_text)

        results.append(
            {
                "chunk_index": i,
                "article_number": chunk.get("article_number"),
                "context_text": context_text,
                "metadata": metadata,
                "chunk_text_preview": chunk_text[:200],
            }
        )

        print(f"  Context: {context_text[:100]}...")
        print(
            f"  Metadata: article={metadata.get('article_number')}, "
            f"book={metadata.get('book_number')}, "
            f"section={metadata.get('section_number')}"
        )

    total_time = time.time() - start_time

    # Get stats
    stats = contextualizer.get_stats()
    contextualizer.print_stats()

    return {
        "provider": "Groq",
        "model": model,
        "results": results,
        "stats": stats,
        "total_time": total_time,
        "avg_time_per_chunk": total_time / len(chunks),
    }


def compare_results(openai_result: dict, groq_result: dict) -> dict:
    """Compare OpenAI vs Groq results."""
    print("\n" + "=" * 80)
    print("📊 COMPARISON REPORT")
    print("=" * 80)

    # Speed comparison
    print("\n⚡ Speed:")
    print(f"  OpenAI ({openai_result['model']}): {openai_result['avg_time_per_chunk']:.3f}s/chunk")
    print(f"  Groq ({groq_result['model']}): {groq_result['avg_time_per_chunk']:.3f}s/chunk")
    speedup = openai_result["avg_time_per_chunk"] / groq_result["avg_time_per_chunk"]
    print(f"  → Groq is {speedup:.1f}x faster")

    # Cost comparison
    print("\n💰 Cost:")
    openai_cost = openai_result["stats"]["total_cost_usd"]
    groq_cost = groq_result["stats"]["total_cost_usd"]
    print(
        f"  OpenAI: ${openai_cost:.6f} total, ${openai_cost / len(openai_result['results']):.6f}/chunk"
    )
    print(f"  Groq: ${groq_cost:.6f} total, ${groq_cost / len(groq_result['results']):.6f}/chunk")
    if groq_cost > 0:
        cost_ratio = openai_cost / groq_cost
        print(f"  → Groq is {cost_ratio:.1f}x cheaper")

    # Token usage
    print("\n📝 Token Usage:")
    print("  OpenAI:")
    print(f"    Input: {openai_result['stats']['total_input_tokens']:,}")
    print(f"    Output: {openai_result['stats']['total_output_tokens']:,}")
    print("  Groq:")
    print(f"    Input: {groq_result['stats']['total_input_tokens']:,}")
    print(f"    Output: {groq_result['stats']['total_output_tokens']:,}")

    # Quality comparison
    print("\n🎯 Quality (Metadata Extraction Accuracy):")

    def check_accuracy(results):
        correct_articles = sum(
            1 for r in results if r["metadata"].get("article_number") == r.get("article_number")
        )
        has_structure = sum(
            1
            for r in results
            if r["metadata"].get("book_number") or r["metadata"].get("section_number")
        )
        has_context = sum(1 for r in results if len(r["context_text"]) > 20)
        return correct_articles, has_structure, has_context, len(results)

    openai_acc = check_accuracy(openai_result["results"])
    groq_acc = check_accuracy(groq_result["results"])

    print("  OpenAI:")
    print(
        f"    Article numbers: {openai_acc[0]}/{openai_acc[3]} ({openai_acc[0] / openai_acc[3] * 100:.0f}%)"
    )
    print(
        f"    Structure metadata: {openai_acc[1]}/{openai_acc[3]} ({openai_acc[1] / openai_acc[3] * 100:.0f}%)"
    )
    print(
        f"    Context generated: {openai_acc[2]}/{openai_acc[3]} ({openai_acc[2] / openai_acc[3] * 100:.0f}%)"
    )

    print("  Groq:")
    print(
        f"    Article numbers: {groq_acc[0]}/{groq_acc[3]} ({groq_acc[0] / groq_acc[3] * 100:.0f}%)"
    )
    print(
        f"    Structure metadata: {groq_acc[1]}/{groq_acc[3]} ({groq_acc[1] / groq_acc[3] * 100:.0f}%)"
    )
    print(
        f"    Context generated: {groq_acc[2]}/{groq_acc[3]} ({groq_acc[2] / groq_acc[3] * 100:.0f}%)"
    )

    # Success rate
    print("\n✅ Success Rate:")
    print(f"  OpenAI: {openai_result['stats']['success_rate']:.1%}")
    print(f"  Groq: {groq_result['stats']['success_rate']:.1%}")

    # Recommendation
    print("\n🏆 Recommendation:")

    # Calculate scores (simple weighted scoring)
    openai_score = (
        (1.0 / openai_result["avg_time_per_chunk"]) * 0.3  # Speed (30%)
        + (1.0 / (openai_cost + 0.0001)) * 0.3  # Cost (30%)
        + (openai_acc[0] / openai_acc[3]) * 0.4  # Accuracy (40%)
    )

    groq_score = (
        (1.0 / groq_result["avg_time_per_chunk"]) * 0.3  # Speed (30%)
        + (1.0 / (groq_cost + 0.0001)) * 0.3  # Cost (30%)
        + (groq_acc[0] / groq_acc[3]) * 0.4  # Accuracy (40%)
    )

    if groq_score > openai_score * 1.1:
        print("  ✨ Groq is the clear winner!")
        print(f"     - {speedup:.1f}x faster")
        print(f"     - {cost_ratio:.1f}x cheaper" if groq_cost > 0 else "     - Much cheaper")
        print("     - Similar/better accuracy")
    elif openai_score > groq_score * 1.1:
        print("  ✨ OpenAI is better for quality-critical tasks")
    else:
        print("  ✨ Both APIs are comparable - choose based on preference:")
        print("     - Groq: faster and cheaper")
        print("     - OpenAI: more stable/established")

    print("\n" + "=" * 80)

    # Return comparison data
    return {
        "openai": openai_result,
        "groq": groq_result,
        "comparison": {
            "speedup_groq": speedup,
            "cost_ratio": cost_ratio if groq_cost > 0 else None,
            "openai_accuracy": openai_acc,
            "groq_accuracy": groq_acc,
        },
    }


async def main():
    """Main A/B test."""
    print("\n" + "=" * 80)
    print("🔬 A/B TEST: OpenAI vs Groq for Contextual RAG")
    print("=" * 80)

    # Configuration
    pdf_path = "/home/admin/Ukraine_Criminal_Code_as_of_2010_RU.pdf"
    num_chunks = 10

    # Models to test
    openai_model = "gpt-4o-mini"  # Cheapest option
    groq_model = "llama-3.1-8b-instant"  # Fastest, cheapest

    print("\nConfiguration:")
    print("  PDF: Criminal Code of Ukraine")
    print(f"  Chunks: {num_chunks}")
    print(f"  OpenAI Model: {openai_model}")
    print(f"  Groq Model: {groq_model}")

    # Load chunks
    chunks = load_test_chunks(pdf_path, num_chunks)

    # Test OpenAI
    openai_result = await test_openai(chunks, openai_model)

    # Test Groq
    groq_result = await test_groq(chunks, groq_model)

    # Compare
    comparison = compare_results(openai_result, groq_result)

    # Save results
    output_file = "/home/admin/api_comparison_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ A/B Test Complete!")


if __name__ == "__main__":
    asyncio.run(main())
