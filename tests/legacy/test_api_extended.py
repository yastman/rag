#!/usr/bin/env python3
"""
Extended API Test: OpenAI + Groq (12 models total)
"""

import asyncio
import json
import time

from dotenv import load_dotenv


load_dotenv()

from contextualize_groq_async import ContextualRetrievalGroqAsync
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
from pymupdf_chunker import PyMuPDFChunker


# Extended test: 12 models across all tiers
EXTENDED_MODELS = [
    # === BUDGET TIER (cheap + fast) ===
    {
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "label": "Llama 3.1 8B (840 TPS)",
        "tier": "budget",
    },
    {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "label": "GPT OSS 20B (1000 TPS)",
        "tier": "budget",
    },
    {"provider": "openai", "model": "gpt-4o-mini", "label": "GPT-4o mini", "tier": "budget"},
    {"provider": "openai", "model": "gpt-4.1-mini", "label": "GPT-4.1 mini", "tier": "budget"},
    # === MID TIER (balance) ===
    {
        "provider": "groq",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "label": "Llama 4 Scout (MoE 17Bx16)",
        "tier": "mid",
    },
    {"provider": "groq", "model": "qwen/qwen3-32b", "label": "Qwen3 32B", "tier": "mid"},
    {
        "provider": "groq",
        "model": "meta-llama/llama-guard-4-12b",
        "label": "Llama Guard 4 12B",
        "tier": "mid",
    },
    # === PREMIUM TIER (quality) ===
    {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B",
        "tier": "premium",
    },
    {
        "provider": "groq",
        "model": "meta-llama/llama-4-maverick-17b-128e-instruct",
        "label": "Llama 4 Maverick (MoE 17Bx128)",
        "tier": "premium",
    },
    {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "label": "GPT OSS 120B",
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
    print(f"🤖 {label} ({tier})")
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

            _context_text, metadata = await contextualizer.situate_context_with_metadata(chunk_text)

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
            full_doc_cost = cost_per_chunk * 448  # Criminal Code
            print(f"   Cost: ${stats['total_cost_usd']:.6f} (${cost_per_chunk:.6f}/chunk)")
            print(f"   Full Document (448 chunks): ${full_doc_cost:.2f}")
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


def print_comparison_table(all_results: list[dict]):
    """Print comprehensive comparison table."""
    print("\n" + "=" * 100)
    print("📊 COMPREHENSIVE COMPARISON TABLE")
    print("=" * 100)

    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]

    if not successful:
        print("\n❌ No successful tests")
        return

    # Header
    print(
        f"\n{'Model':<40} {'Tier':>10} {'Speed':>10} {'Cost/chunk':>12} {'Full Doc':>10} {'Accuracy':>10}"
    )
    print("-" * 100)

    # Group by tier
    for tier in ["budget", "mid", "premium"]:
        tier_models = [r for r in successful if r["tier"] == tier]
        if tier_models:
            print(f"\n{tier.upper()}:")
            for result in sorted(tier_models, key=lambda x: x["avg_time_per_chunk"]):
                label = result["label"]
                speed = result["avg_time_per_chunk"]
                cost = result["stats"].get("total_cost_usd", 0) / len(result["results"])
                full_cost = cost * 448
                accuracy = result["accuracy"]

                print(
                    f"  {label:<38} {tier:>10} {speed:>8.2f}s ${cost:>10.6f} ${full_cost:>9.2f} {accuracy:>9.0%}"
                )

    # Best options
    print("\n" + "=" * 100)
    print("🏆 BEST OPTIONS")
    print("=" * 100)

    fastest = min(successful, key=lambda x: x["avg_time_per_chunk"])
    cheapest = min(
        successful, key=lambda x: x["stats"].get("total_cost_usd", 999) / len(x["results"])
    )
    most_accurate = max(successful, key=lambda x: x["accuracy"])

    # Best balance (quality/price ratio)
    balanced = max(
        [r for r in successful if r["accuracy"] >= 0.9],
        key=lambda x: (
            x["accuracy"] / (x["stats"].get("total_cost_usd", 0.001) / len(x["results"]) + 0.000001)
        ),
    )

    print(f"\n⚡ Fastest: {fastest['label']}")
    print(f"   {fastest['avg_time_per_chunk']:.2f}s/chunk, {fastest['accuracy']:.0%} accuracy")

    print(f"\n💰 Cheapest: {cheapest['label']}")
    cost_per_chunk = cheapest["stats"].get("total_cost_usd", 0) / len(cheapest["results"])
    print(
        f"   ${cost_per_chunk:.6f}/chunk (${cost_per_chunk * 448:.2f} for 448 chunks), {cheapest['accuracy']:.0%} accuracy"
    )

    print(f"\n🎯 Most Accurate: {most_accurate['label']}")
    print(
        f"   {most_accurate['accuracy']:.0%} accuracy, {most_accurate['avg_time_per_chunk']:.2f}s/chunk"
    )

    print(f"\n💎 Best Balance: {balanced['label']}")
    cost_per_chunk = balanced["stats"].get("total_cost_usd", 0) / len(balanced["results"])
    print(
        f"   {balanced['accuracy']:.0%} accuracy, {balanced['avg_time_per_chunk']:.2f}s/chunk, ${cost_per_chunk * 448:.2f}/document"
    )

    # Cost comparison for full Criminal Code
    print("\n" + "=" * 100)
    print("💵 COST ESTIMATE - Full Criminal Code (448 chunks)")
    print("=" * 100)

    for tier in ["budget", "mid", "premium"]:
        tier_models = [r for r in successful if r["tier"] == tier]
        if tier_models:
            print(f"\n{tier.upper()}:")
            for result in sorted(
                tier_models, key=lambda x: x["stats"].get("total_cost_usd", 0) / len(x["results"])
            ):
                label = result["label"]
                cost_per_chunk = result["stats"].get("total_cost_usd", 0) / len(result["results"])
                full_cost = cost_per_chunk * 448
                full_time = result["avg_time_per_chunk"] * 448

                print(
                    f"  {label:<38} ${full_cost:>8.2f} (~{full_time / 60:>5.1f} min, {result['accuracy']:.0%} accuracy)"
                )

    # Failed models
    if failed:
        print("\n" + "=" * 100)
        print("❌ FAILED MODELS")
        print("=" * 100)
        for result in failed:
            print(f"  {result['label']}: {result['error'][:100]}")

    print("\n" + "=" * 100)


async def main():
    """Main test."""
    print("\n" + "=" * 100)
    print("🔬 EXTENDED API COMPARISON: 10 Models (OpenAI + Groq)")
    print("=" * 100)

    pdf_path = "/srv/Ukraine_Criminal_Code_as_of_2010_RU.pdf"
    num_chunks = 10

    # Load chunks
    chunks = load_test_chunks(pdf_path, num_chunks)

    all_results = []

    # Test all models
    for i, model_config in enumerate(EXTENDED_MODELS, 1):
        print(f"\n[{i}/{len(EXTENDED_MODELS)}] Testing {model_config['label']}...")

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
    print_comparison_table(all_results)

    # Save results
    output_file = "/srv/api_comparison_extended_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Extended Test Complete!")


if __name__ == "__main__":
    asyncio.run(main())
