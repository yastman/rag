#!/usr/bin/env python3
"""
Multi-Model A/B Test: OpenAI GPT-5 vs Groq
Comprehensive comparison across budget/mid/premium tiers
"""

import asyncio
import json
import time

from dotenv import load_dotenv


load_dotenv()

from contextualize_groq_async import ContextualRetrievalGroqAsync
from contextualize_openai_async import ContextualRetrievalOpenAIAsync
from pymupdf_chunker import PyMuPDFChunker


# Test configuration
MODELS_TO_TEST = {
    "budget": [
        {"provider": "openai", "model": "gpt-5-nano", "label": "GPT-5 nano"},
        {"provider": "groq", "model": "llama-3.1-8b-instant", "label": "Llama 3.1 8B (840 TPS)"},
        {"provider": "groq", "model": "grok-1", "label": "GPT OSS 20B (1000 TPS)"},
    ],
    "mid": [
        {"provider": "openai", "model": "gpt-5-mini", "label": "GPT-5 mini"},
        {"provider": "groq", "model": "llama-4-scout", "label": "Llama 4 Scout (MoE 17Bx16)"},
        {"provider": "groq", "model": "qwen-32b", "label": "Qwen3 32B"},
    ],
    "premium": [
        {"provider": "openai", "model": "gpt-5", "label": "GPT-5"},
        {"provider": "groq", "model": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B"},
        {
            "provider": "groq",
            "model": "llama-4-maverick",
            "label": "Llama 4 Maverick (MoE 17Bx128)",
        },
    ],
}


def load_test_chunks(pdf_path: str, num_chunks: int = 10) -> list[dict]:
    """Load test chunks from PDF."""
    print(f"📄 Loading {num_chunks} chunks from Criminal Code...")

    chunker = PyMuPDFChunker(
        target_chunk_size=600, min_chunk_size=400, max_chunk_size=800, overlap_percent=0.12
    )

    chunks = chunker.chunk_pdf(pdf_path)

    # Select diverse chunks
    if len(chunks) <= num_chunks:
        selected = chunks
    else:
        step = len(chunks) // num_chunks
        selected = [chunks[i * step] for i in range(num_chunks)]

    print(f"✓ Loaded {len(selected)} chunks")
    print(f"  Sample articles: {[c.get('article_number') for c in selected[:5]]}")

    return selected


async def test_model(provider: str, model: str, label: str, chunks: list[dict]) -> dict:
    """Test a single model."""
    print(f"\n{'=' * 80}")
    print(f"🤖 Testing {label} ({provider}/{model})...")
    print(f"{'=' * 80}")

    # Initialize contextualizer
    if provider == "openai":
        contextualizer = ContextualRetrievalOpenAIAsync(model=model, max_concurrent=5)
    else:  # groq
        contextualizer = ContextualRetrievalGroqAsync(model=model, max_concurrent=10)

    results = []
    start_time = time.time()

    for i, chunk in enumerate(chunks):
        chunk_text = chunk["text"]
        print(
            f"\n[{i + 1}/{len(chunks)}] Processing article {chunk.get('article_number', '?')}...",
            end=" ",
        )

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

        # Quick status
        article_match = metadata.get("article_number") == chunk.get("article_number")
        print(f"{'✓' if article_match else '✗'} article={metadata.get('article_number')}")

    total_time = time.time() - start_time

    # Get stats
    stats = contextualizer.get_stats()

    # Print summary
    print(f"\n📊 {label} Summary:")
    print(f"  Time: {total_time:.2f}s ({total_time / len(chunks):.2f}s/chunk)")
    print(f"  Tokens: {stats['total_input_tokens']:,} in / {stats['total_output_tokens']:,} out")
    if "total_cost_usd" in stats:
        print(
            f"  Cost: ${stats['total_cost_usd']:.6f} (${stats['total_cost_usd'] / len(chunks):.6f}/chunk)"
        )
    print(f"  Success: {stats['success_rate']:.0%}")

    return {
        "provider": provider,
        "model": model,
        "label": label,
        "results": results,
        "stats": stats,
        "total_time": total_time,
        "avg_time_per_chunk": total_time / len(chunks),
    }


def calculate_accuracy(results: list[dict]) -> dict:
    """Calculate accuracy metrics."""
    total = len(results)

    correct_articles = sum(
        1 for r in results if r["metadata"].get("article_number") == r.get("article_number")
    )

    has_structure = sum(
        1
        for r in results
        if r["metadata"].get("book_number") or r["metadata"].get("section_number")
    )

    has_context = sum(1 for r in results if len(r["context_text"]) > 20)

    return {
        "article_accuracy": correct_articles / total,
        "structure_rate": has_structure / total,
        "context_rate": has_context / total,
        "overall_score": (correct_articles + has_structure + has_context) / (total * 3),
    }


def print_comparison_table(all_results: dict):
    """Print comprehensive comparison table."""
    print("\n" + "=" * 100)
    print("📊 COMPREHENSIVE COMPARISON - ALL MODELS")
    print("=" * 100)

    # Header
    print(
        f"\n{'Model':<25} {'Speed':>10} {'Cost/chunk':>12} {'Accuracy':>10} {'Success':>8} {'Score':>8}"
    )
    print("-" * 100)

    # Collect data for ranking
    model_scores = []

    for tier in ["budget", "mid", "premium"]:
        print(f"\n{tier.upper()} TIER:")
        for result in all_results[tier]:
            label = result["label"]
            speed = result["avg_time_per_chunk"]
            cost = result["stats"].get("total_cost_usd", 0) / len(result["results"])
            accuracy = calculate_accuracy(result["results"])
            success = result["stats"]["success_rate"]

            # Calculate weighted score (higher is better)
            # Speed: inverse (faster = better)
            # Cost: inverse (cheaper = better)
            # Accuracy: direct (higher = better)
            # Success: direct (higher = better)
            score = (
                (1.0 / speed) * 0.2  # Speed 20%
                + (1.0 / (cost + 0.00001)) * 0.3  # Cost 30%
                + accuracy["overall_score"] * 0.4  # Accuracy 40%
                + success * 0.1  # Success 10%
            )

            model_scores.append(
                {
                    "tier": tier,
                    "label": label,
                    "score": score,
                    "speed": speed,
                    "cost": cost,
                    "accuracy": accuracy,
                    "success": success,
                }
            )

            print(
                f"  {label:<23} {speed:>8.2f}s ${cost:>10.6f} {accuracy['article_accuracy']:>9.0%} {success:>7.0%} {score:>8.2f}"
            )

    # Rankings
    print("\n" + "=" * 100)
    print("🏆 RANKINGS")
    print("=" * 100)

    # Overall ranking
    model_scores.sort(key=lambda x: x["score"], reverse=True)
    print("\n🥇 Overall Best (by weighted score):")
    for i, model in enumerate(model_scores[:3], 1):
        print(f"  {i}. {model['label']} - Score: {model['score']:.2f} ({model['tier']} tier)")

    # Best by speed
    fastest = min(model_scores, key=lambda x: x["speed"])
    print(f"\n⚡ Fastest: {fastest['label']} ({fastest['speed']:.2f}s/chunk)")

    # Best by cost
    cheapest = min(model_scores, key=lambda x: x["cost"])
    print(f"\n💰 Cheapest: {cheapest['label']} (${cheapest['cost']:.6f}/chunk)")

    # Best by accuracy
    most_accurate = max(model_scores, key=lambda x: x["accuracy"]["article_accuracy"])
    print(
        f"\n🎯 Most Accurate: {most_accurate['label']} ({most_accurate['accuracy']['article_accuracy']:.0%} article match)"
    )

    # Recommendations
    print("\n" + "=" * 100)
    print("💡 RECOMMENDATIONS")
    print("=" * 100)

    print("\n1. For Mass Processing (speed + cost):")
    # Find best speed/cost ratio in budget tier
    budget_models = [m for m in model_scores if m["tier"] == "budget"]
    best_budget = max(budget_models, key=lambda x: x["score"])
    print(f"   → {best_budget['label']}")
    print(
        f"     Speed: {best_budget['speed']:.2f}s, Cost: ${best_budget['cost']:.6f}, Accuracy: {best_budget['accuracy']['article_accuracy']:.0%}"
    )

    print("\n2. For Quality (accuracy + reliability):")
    # Find best accuracy with success rate
    quality_models = [
        m for m in model_scores if m["accuracy"]["article_accuracy"] >= 0.8 and m["success"] >= 0.9
    ]
    if quality_models:
        best_quality = max(quality_models, key=lambda x: x["accuracy"]["article_accuracy"])
        print(f"   → {best_quality['label']}")
        print(
            f"     Accuracy: {best_quality['accuracy']['article_accuracy']:.0%}, Cost: ${best_quality['cost']:.6f}"
        )

    print("\n3. Best Balance (quality/price ratio):")
    # Find model with good accuracy but not most expensive
    mid_premium = [m for m in model_scores if m["tier"] in ["mid", "premium"]]
    if mid_premium:
        best_balance = max(
            mid_premium, key=lambda x: x["accuracy"]["article_accuracy"] / (x["cost"] + 0.00001)
        )
        print(f"   → {best_balance['label']}")
        print(
            f"     Accuracy: {best_balance['accuracy']['article_accuracy']:.0%}, Cost: ${best_balance['cost']:.6f}, Speed: {best_balance['speed']:.2f}s"
        )

    # Cost comparison for full Criminal Code (448 chunks)
    print("\n" + "=" * 100)
    print("💵 COST ESTIMATE - Full Criminal Code (448 chunks)")
    print("=" * 100)

    for tier in ["budget", "mid", "premium"]:
        print(f"\n{tier.upper()} TIER:")
        tier_models = [m for m in model_scores if m["tier"] == tier]
        for model in sorted(tier_models, key=lambda x: x["cost"]):
            full_cost = model["cost"] * 448
            full_time = model["speed"] * 448
            print(f"  {model['label']:<23} ${full_cost:>8.2f} (~{full_time / 60:>5.1f} min)")

    print("\n" + "=" * 100)


async def main():
    """Main multi-model test."""
    print("\n" + "=" * 100)
    print("🔬 MULTI-MODEL COMPARISON: OpenAI GPT-5 vs Groq")
    print("=" * 100)

    # Configuration
    pdf_path = "/srv/Ukraine_Criminal_Code_as_of_2010_RU.pdf"
    num_chunks = 10

    print("\nConfiguration:")
    print("  PDF: Criminal Code of Ukraine")
    print(f"  Chunks: {num_chunks}")
    print("  Tiers: Budget, Mid, Premium")

    # Load chunks once
    chunks = load_test_chunks(pdf_path, num_chunks)

    # Test all models
    all_results = {}

    for tier, models in MODELS_TO_TEST.items():
        all_results[tier] = []

        for model_config in models:
            result = await test_model(
                provider=model_config["provider"],
                model=model_config["model"],
                label=model_config["label"],
                chunks=chunks,
            )
            all_results[tier].append(result)

            # Small delay between models
            await asyncio.sleep(2)

    # Print comparison
    print_comparison_table(all_results)

    # Save results
    output_file = "/srv/api_comparison_multi_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Multi-Model Test Complete!")


if __name__ == "__main__":
    asyncio.run(main())
