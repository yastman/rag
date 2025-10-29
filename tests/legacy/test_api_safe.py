#!/usr/bin/env python3
"""
Safe Multi-Model Test: Start with verified models, expand gradually
"""

import asyncio
import json
import time

from dotenv import load_dotenv


load_dotenv()

from contextualize_groq_async import ContextualRetrievalGroqAsync
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
from pymupdf_chunker import PyMuPDFChunker


# Phase 1: Budget tier (дешёвые и быстрые)
PHASE_1_MODELS = [
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
    {"provider": "openai", "model": "gpt-5-nano", "label": "GPT-5 nano", "tier": "budget"},
    {"provider": "openai", "model": "gpt-4o-mini", "label": "GPT-4o mini", "tier": "budget"},
]

# Phase 2: Mid tier (баланс цена/качество)
PHASE_2_MODELS = [
    {
        "provider": "groq",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "label": "Llama 4 Scout (MoE)",
        "tier": "mid",
    },
    {"provider": "groq", "model": "qwen/qwen3-32b", "label": "Qwen3 32B", "tier": "mid"},
    {"provider": "openai", "model": "gpt-5-mini", "label": "GPT-5 mini", "tier": "mid"},
]

# Phase 3: Premium tier (максимальное качество)
PHASE_3_MODELS = [
    {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B",
        "tier": "premium",
    },
    {
        "provider": "groq",
        "model": "meta-llama/llama-4-maverick-17b-128e-instruct",
        "label": "Llama 4 Maverick (MoE)",
        "tier": "premium",
    },
    {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "label": "GPT OSS 120B",
        "tier": "premium",
    },
    {"provider": "openai", "model": "gpt-5", "label": "GPT-5", "tier": "premium"},
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

    print(
        f"✓ Loaded {len(selected)} chunks (articles: {[c.get('article_number') for c in selected[:5]]}...)"
    )
    return selected


async def test_model(provider: str, model: str, label: str, tier: str, chunks: list[dict]) -> dict:
    """Test a single model."""
    print(f"\n{'=' * 80}")
    print(f"🤖 Testing {label} ({tier} tier)")
    print(f"   Provider: {provider}, Model: {model}")
    print(f"{'=' * 80}")

    try:
        # Initialize contextualizer
        if provider == "openai":
            contextualizer = ContextualRetrievalOpenAIAsync(model=model, max_concurrent=5)
        else:  # groq
            contextualizer = ContextualRetrievalGroqAsync(model=model, max_concurrent=10)

        results = []
        start_time = time.time()

        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            print(f"[{i + 1}/{len(chunks)}] Article {chunk.get('article_number', '?')}...", end=" ")

            context_text, metadata = await contextualizer.situate_context_with_metadata(chunk_text)

            results.append(
                {
                    "chunk_index": i,
                    "article_number": chunk.get("article_number"),
                    "context_text": context_text,
                    "metadata": metadata,
                }
            )

            # Quick status
            article_match = metadata.get("article_number") == chunk.get("article_number")
            print(f"{'✓' if article_match else '✗'}")

        total_time = time.time() - start_time

        # Get stats
        stats = contextualizer.get_stats()

        # Calculate accuracy
        correct_articles = sum(
            1 for r in results if r["metadata"].get("article_number") == r.get("article_number")
        )
        accuracy = correct_articles / len(results)

        # Summary
        print("\n📊 Summary:")
        print(f"   Time: {total_time:.2f}s ({total_time / len(chunks):.2f}s/chunk)")
        print(
            f"   Tokens: {stats['total_input_tokens']:,} in / {stats['total_output_tokens']:,} out"
        )
        if "total_cost_usd" in stats:
            cost_per_chunk = stats["total_cost_usd"] / len(chunks)
            print(f"   Cost: ${stats['total_cost_usd']:.6f} (${cost_per_chunk:.6f}/chunk)")
        print(f"   Accuracy: {accuracy:.0%}")
        print(f"   Success: {stats['success_rate']:.0%}")

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
    """Print comparison table."""
    print("\n" + "=" * 100)
    print("📊 COMPARISON TABLE")
    print("=" * 100)

    # Filter successful results
    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]

    if not successful:
        print("\n❌ No successful tests to compare")
        return

    # Header
    print(f"\n{'Model':<30} {'Tier':>10} {'Speed':>10} {'Cost/chunk':>12} {'Accuracy':>10}")
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
                accuracy = result["accuracy"]

                print(f"  {label:<28} {tier:>10} {speed:>8.2f}s ${cost:>10.6f} {accuracy:>9.0%}")

    # Cost estimate for full Criminal Code (448 chunks)
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

                print(f"  {label:<28} ${full_cost:>8.2f} (~{full_time / 60:>5.1f} min)")

    # Recommendations
    print("\n" + "=" * 100)
    print("💡 RECOMMENDATIONS")
    print("=" * 100)

    # Best budget option
    budget_models = [r for r in successful if r["tier"] == "budget"]
    if budget_models:
        best_budget = min(
            budget_models, key=lambda x: x["stats"].get("total_cost_usd", 999) / len(x["results"])
        )
        print(f"\n💰 Best Budget: {best_budget['label']}")
        cost = best_budget["stats"].get("total_cost_usd", 0) / len(best_budget["results"])
        print(
            f"   ${cost:.6f}/chunk, {best_budget['avg_time_per_chunk']:.2f}s/chunk, {best_budget['accuracy']:.0%} accuracy"
        )

    # Fastest
    fastest = min(successful, key=lambda x: x["avg_time_per_chunk"])
    print(f"\n⚡ Fastest: {fastest['label']}")
    print(f"   {fastest['avg_time_per_chunk']:.2f}s/chunk")

    # Most accurate
    most_accurate = max(successful, key=lambda x: x["accuracy"])
    print(f"\n🎯 Most Accurate: {most_accurate['label']}")
    print(f"   {most_accurate['accuracy']:.0%} accuracy")

    # Failed models
    if failed:
        print("\n❌ Failed Models:")
        for result in failed:
            print(f"   {result['label']}: {result['error']}")

    print("\n" + "=" * 100)


async def main():
    """Main test."""
    print("\n" + "=" * 100)
    print("🔬 SAFE MULTI-MODEL COMPARISON TEST")
    print("=" * 100)

    pdf_path = "/srv/Ukraine_Criminal_Code_as_of_2010_RU.pdf"
    num_chunks = 10

    print("\nConfiguration:")
    print("  PDF: Criminal Code of Ukraine")
    print(f"  Chunks: {num_chunks}")
    print("  Strategy: Test verified models first, expand gradually")

    # Load chunks
    chunks = load_test_chunks(pdf_path, num_chunks)

    all_results = []

    # Phase 1: Budget tier
    print(f"\n{'=' * 100}")
    print("PHASE 1: Budget Tier (Speed + Cost)")
    print(f"{'=' * 100}")

    for model_config in PHASE_1_MODELS:
        result = await test_model(
            provider=model_config["provider"],
            model=model_config["model"],
            label=model_config["label"],
            tier=model_config["tier"],
            chunks=chunks,
        )
        all_results.append(result)
        await asyncio.sleep(1)

    # Phase 2: Mid tier
    print(f"\n{'=' * 100}")
    print("PHASE 2: Mid Tier (Balance)")
    print(f"{'=' * 100}")

    for model_config in PHASE_2_MODELS:
        result = await test_model(
            provider=model_config["provider"],
            model=model_config["model"],
            label=model_config["label"],
            tier=model_config["tier"],
            chunks=chunks,
        )
        all_results.append(result)
        await asyncio.sleep(1)

    # Phase 3: Premium tier
    print(f"\n{'=' * 100}")
    print("PHASE 3: Premium Tier (Quality)")
    print(f"{'=' * 100}")

    for model_config in PHASE_3_MODELS:
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
    output_file = "/srv/api_comparison_safe_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Test Complete!")


if __name__ == "__main__":
    asyncio.run(main())
