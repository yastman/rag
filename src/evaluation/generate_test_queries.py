#!/usr/bin/env python3
"""
Generate test queries using LLM.
Creates 3 types of queries for each article:
1. Direct (exact query)
2. Semantic (semantic variant)
3. Paraphrased (paraphrased)
"""

import asyncio
import json
import sys

from qdrant_client import QdrantClient, models


sys.path.append("/srv/contextual_rag")
from contextualize_groq_async import ContextualRetrievalGroqAsync

from src.config import Settings


# Load settings
_settings = Settings()
QDRANT_URL = _settings.qdrant_url
QDRANT_API_KEY = _settings.qdrant_api_key or ""


def _make_client() -> QdrantClient:
    """Create a QdrantClient from resolved settings."""
    if QDRANT_API_KEY:
        return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return QdrantClient(url=QDRANT_URL)


def fetch_article_texts(collection_name: str, article_numbers: list[str]) -> dict[str, str]:
    """
    Fetch full texts for specified articles from Qdrant.

    Args:
        collection_name: Qdrant collection
        article_numbers: List of article numbers to fetch (as strings)

    Returns:
        Dict mapping article_number (str) -> full_text
    """
    print(f"Fetching {len(article_numbers)} articles from Qdrant...")

    client = _make_client()
    articles = {}

    for article_num in article_numbers:
        # Search for article by article_number filter
        # IMPORTANT: Qdrant stores article_number as int, not string!
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="article_number",
                    match=models.MatchValue(value=int(article_num)),
                )
            ]
        )

        points, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        if points:
            text = (points[0].payload or {}).get("text", "")
            articles[article_num] = text
            print(f"  Article {article_num}: {len(text)} chars")
        else:
            print(f"  Article {article_num}: NOT FOUND")

    print(f"Fetched {len(articles)}/{len(article_numbers)} articles\n")
    return articles


async def generate_queries_for_article(
    llm: ContextualRetrievalGroqAsync, article_num: str, article_text: str
) -> list[dict]:
    """
    Generate 3 types of queries for a single article.

    Returns:
        List of query objects with type and expected_article
    """
    # Truncate text if too long
    text_preview = article_text[:1000] if len(article_text) > 1000 else article_text

    prompt = f"""Ты эксперт по Уголовному кодексу Украины. На основе текста статьи {article_num}, создай 3 поисковых запроса:

ТЕКСТ СТАТЬИ {article_num}:
{text_preview}

ЗАДАЧА: Создай 3 запроса, которые пользователь может ввести для поиска этой статьи:

1. ПРЯМОЙ ЗАПРОС (direct): точный, упоминает номер статьи или её ключевое понятие
   Пример: "статья 115" или "умышленное убийство"

2. СЕМАНТИЧЕСКИЙ (semantic): описывает суть статьи своими словами
   Пример: "какое наказание за преднамеренное лишение жизни человека"

3. ПЕРЕФРАЗИРОВАННЫЙ (paraphrased): вопрос с перефразированием
   Пример: "что грозит за убийство по УК Украины"

ВАЖНО:
- Запросы должны быть короткими (5-15 слов)
- Каждый запрос должен логически вести к этой статье
- Используй естественный язык, как будто спрашивает обычный человек

ОТВЕТ в формате JSON:
{{
  "direct": "...",
  "semantic": "...",
  "paraphrased": "..."
}}"""

    # Call LLM using aiohttp directly
    import aiohttp

    async with (
        aiohttp.ClientSession() as session,
        session.post(
            llm.api_url,
            headers={"Authorization": f"Bearer {llm.api_key}", "Content-Type": "application/json"},
            json={
                "model": llm.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": llm.max_tokens,
            },
        ) as resp,
    ):
        response = await resp.json()

    # Parse JSON response
    content = response["choices"][0]["message"]["content"]

    # Extract JSON from response (in case there's extra text)
    start_idx = content.find("{")
    end_idx = content.rfind("}") + 1
    json_str = content[start_idx:end_idx]

    queries_dict = json.loads(json_str)

    # Create query objects
    return [
        {
            "query": queries_dict["direct"],
            "type": "direct",
            "expected_article": article_num,  # Already a string
            "difficulty": "easy",
        },
        {
            "query": queries_dict["semantic"],
            "type": "semantic",
            "expected_article": article_num,  # Already a string
            "difficulty": "medium",
        },
        {
            "query": queries_dict["paraphrased"],
            "type": "paraphrased",
            "expected_article": article_num,  # Already a string
            "difficulty": "hard",
        },
    ]


async def generate_all_queries(
    article_texts: dict[str, str], model: str = "openai/gpt-oss-120b", max_concurrent: int = 5
) -> list[dict]:
    """
    Generate queries for all articles asynchronously.

    Args:
        article_texts: Dict mapping article_number (str) -> text
        model: LLM model to use
        max_concurrent: Max parallel requests

    Returns:
        List of all generated queries
    """
    print(f"Generating queries with {model}...")
    print(f"   Max concurrent: {max_concurrent}")
    print(f"   Total articles: {len(article_texts)}\n")

    # Initialize LLM
    llm = ContextualRetrievalGroqAsync(model=model, max_concurrent=max_concurrent)

    all_queries = []
    completed = 0

    # Create async tasks
    tasks = []
    for article_num, text in article_texts.items():
        task = generate_queries_for_article(llm, article_num, text)
        tasks.append((article_num, task))

    # Process with progress tracking
    for article_num, task_coro in tasks:
        try:
            queries = await task_coro
            all_queries.extend(queries)
            completed += 1
            print(f"[{completed}/{len(tasks)}] Article {article_num}: 3 queries generated")
        except Exception as e:
            print(f"[{completed}/{len(tasks)}] Article {article_num}: ERROR: {e}")
            completed += 1

    print(f"\nGenerated {len(all_queries)} queries total")

    # Print stats
    llm.print_stats()

    return all_queries


def select_representative_articles(all_articles: dict[str, list], n: int = 50) -> list[str]:
    """
    Select N representative articles distributed across the entire Criminal Code.

    Args:
        all_articles: Ground truth articles
        n: Number of articles to select

    Returns:
        List of article numbers (as strings)
    """
    # Get all article numbers (keep as strings to match Qdrant)
    article_nums = sorted(all_articles.keys(), key=lambda x: int(x))

    # Select evenly distributed articles
    step = len(article_nums) // n
    selected = [article_nums[i * step] for i in range(n)]

    # Convert to int for display
    selected_ints = [int(a) for a in selected]

    print(f"Selected {len(selected)} articles:")
    print(f"   Range: {min(selected_ints)} - {max(selected_ints)}")
    print(f"   Sample: {selected_ints[:10]}...")

    return selected


async def main():
    """Main entry point."""
    print("=" * 80)
    print("TEST QUERY GENERATION - Criminal Code Ukraine")
    print("=" * 80)

    collection_name = "ukraine_criminal_code_zai_full"
    num_articles = 50

    # Load ground truth
    ground_truth_file = "evaluation/data/ground_truth_articles.json"
    with open(ground_truth_file, encoding="utf-8") as f:
        all_articles = json.load(f)

    # Select representative articles
    print(f"\nStep 1: Select {num_articles} representative articles")
    selected_articles = select_representative_articles(all_articles, n=num_articles)

    # Fetch article texts
    print("\nStep 2: Fetch article texts from Qdrant")
    article_texts = fetch_article_texts(collection_name, selected_articles)

    # Generate queries
    print("Step 3: Generate test queries with LLM")
    queries = await generate_all_queries(
        article_texts,
        model="openai/gpt-oss-120b",  # 120B parameters, 100% accuracy
        max_concurrent=5,
    )

    # Save queries
    output_file = "evaluation/data/queries_testset.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(queries)} queries to: {output_file}")

    # Print summary
    print("\nTest Set Summary:")
    print(f"   Total queries: {len(queries)}")
    print(f"   Direct: {len([q for q in queries if q['type'] == 'direct'])}")
    print(f"   Semantic: {len([q for q in queries if q['type'] == 'semantic'])}")
    print(f"   Paraphrased: {len([q for q in queries if q['type'] == 'paraphrased'])}")
    print(f"   Articles covered: {len({q['expected_article'] for q in queries})}")

    print("\nTest query generation completed!")


if __name__ == "__main__":
    asyncio.run(main())
