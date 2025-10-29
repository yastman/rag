#!/usr/bin/env python3
"""
Quick API Test: 5 representative models
"""

import asyncio
import time

from dotenv import load_dotenv


load_dotenv()

from contextualize_groq_async import ContextualRetrievalGroqAsync
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
from pymupdf_chunker import PyMuPDFChunker


# Quick test: 5 representative models
QUICK_MODELS = [
    # Budget
    {
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "label": "Llama 3.1 8B (Budget)",
        "tier": "budget",
    },
    {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "label": "GPT-4o mini (Budget)",
        "tier": "budget",
    },
    # Mid
    {"provider": "groq", "model": "qwen/qwen3-32b", "label": "Qwen3 32B (Mid)", "tier": "mid"},
    {"provider": "openai", "model": "gpt-5-mini", "label": "GPT-5 mini (Mid)", "tier": "mid"},
    # Premium
    {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B (Premium)",
        "tier": "premium",
    },
]


def load_test_chunks(pdf_path: str, num_chunks: int = 10) -> list[dict]:
    """Load test chunks from PDF."""
    print(f"📄 Loading {num_chunks} chunks...")

    chunker = PyMuPDFChunker(
        target_chunk_size=600, min_chunk_size=400, max_chunk_size=800, overlap_percent=0.12
    )

    chunks = chunker.chunk_pdf(pdf_path)

    if len(chunks) <= num_chunks:
        selected = chunks
    else:
        step = len(chunks) // num_chunks
        selected = [chunks[i * step] for i in range(num_chunks)]

    print(f"✓ Loaded {len(selected)} chunks\n")
    return selected


async def test_model(provider: str, model: str, label: str, tier: str, chunks: list[dict]) -> dict:
    """Test a single model."""
    print(f"\n{'=' * 80}")
    print(f"🤖 {label}")
    print(f"{'=' * 80}")

    try:
        # Initialize contextualizer
        if provider == "openai":
            contextualizer = ContextualRetrievalOpenAIAsync(model=model, max_concurrent=5)
        else:
            contextualizer = ContextualRetrievalGroqAsync(model=model, max_concurrent=10)

        results = []
        start_time = time.time()

        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            print(f"[{i + 1}/{len(chunks)}] ", end="", flush=True)

            context_text, metadata = await contextualizer.situate_context_with_metadata(chunk_text)

            results.append(
                {
                    "chunk_index": i,
                    "article_number": chunk.get("article_number"),
                    "metadata": metadata,
                }
            )

            article_match = metadata.get("article_number") == chunk.get("article_number")
            print(f"{'✓' if article_match else '✗'}", end=" ", flush=True)

        print()  # Newline
        total_time = time.time() - start_time

        # Get stats
        stats = contextualizer.get_stats()

        # Calculate accuracy
        correct_articles = sum(
            1 for r in results if r["metadata"].get("article_number") == r.get("article_number")
        )
        accuracy = correct_articles / len(results)

        print("\n📊 Summary:")
        print(f"   Time: {total_time:.2f}s ({total_time / len(chunks):.2f}s/chunk)")
        if "total_cost_usd" in stats:
            cost_per_chunk = stats["total_cost_usd"] / len(chunks)
            print(f"   Cost: ${stats['total_cost_usd']:.6f} (${cost_per_chunk:.6f}/chunk)")
        print(f"   Accuracy: {accuracy:.0%}")

        return {
            "provider": provider,
            "model": model,
            "label": label,
            "tier": tier,
            "results": results,
            "stats": stats,
            "total_time": total_time,
            "avg_time_per_chunk": total_time / len(chunks),
            "accuracy": accuracy,
            "success": True,
        }

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return {
            "provider": provider,
            "model": model,
            "label": label,
            "tier": tier,
            "error": str(e),
            "success": False,
        }


async def main():
    """Main test."""
    print("\n" + "=" * 80)
    print("🔬 QUICK API COMPARISON: 5 Representative Models")
    print("=" * 80)

    pdf_path = "/home/admin/Ukraine_Criminal_Code_as_of_2010_RU.pdf"
    num_chunks = 10

    # Load chunks
    chunks = load_test_chunks(pdf_path, num_chunks)

    all_results = []

    # Test all models
    for model_config in QUICK_MODELS:
        result = await test_model(
            provider=model_config["provider"],
            model=model_config["model"],
            label=model_config["label"],
            tier=model_config["tier"],
            chunks=chunks,
        )
        all_results.append(result)
        await asyncio.sleep(1)

    # Print comparison
    print("\n" + "=" * 80)
    print("📊 COMPARISON SUMMARY")
    print("=" * 80)

    successful = [r for r in all_results if r["success"]]

    if successful:
        print(f"\n{'Model':<35} {'Time':>10} {'Cost/chunk':>12} {'Accuracy':>10}")
        print("-" * 80)

        for result in successful:
            label = result["label"]
            speed = result["avg_time_per_chunk"]
            cost = result["stats"].get("total_cost_usd", 0) / len(result["results"])
            accuracy = result["accuracy"]

            print(f"{label:<35} {speed:>8.2f}s ${cost:>10.6f} {accuracy:>9.0%}")

        # Best options
        print("\n💡 Best Options:")
        fastest = min(successful, key=lambda x: x["avg_time_per_chunk"])
        cheapest = min(
            successful, key=lambda x: x["stats"].get("total_cost_usd", 999) / len(x["results"])
        )
        most_accurate = max(successful, key=lambda x: x["accuracy"])

        print(f"  ⚡ Fastest: {fastest['label']} ({fastest['avg_time_per_chunk']:.2f}s/chunk)")
        print(
            f"  💰 Cheapest: {cheapest['label']} (${cheapest['stats'].get('total_cost_usd', 0) / len(cheapest['results']):.6f}/chunk)"
        )
        print(f"  🎯 Most Accurate: {most_accurate['label']} ({most_accurate['accuracy']:.0%})")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
