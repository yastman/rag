"""Benchmark LLM models via the in-process LiteLLM SDK router and direct Cerebras API.

Usage:
    source .env && uv run python scripts/benchmark_llm.py

Env vars:
    CEREBRAS_API_KEY — provider key used by the SDK router and direct Cerebras API
    OPENAI_API_KEY   — optional provider key for SDK-router OpenAI aliases
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

from src.runtime.llm import create_llm_client


CEREBRAS_URL = "https://api.cerebras.ai/v1"
CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY", "")

# Запросы из реальных Langfuse traces (top-5 самых медленных)
TEST_QUERIES = [
    ("generate", "напиши мне информацию про внж?", 1024),
    ("generate", "Какие условия рассрочек?", 1024),
    ("generate", "Виды внж? Для пенсионеров?", 1024),
    ("generate", "Что есть в Солнечном берегу", 1024),
    ("rewrite", "внж", 200),
    ("rewrite", "рассрочка квартира", 200),
    ("rewrite", "пенсионер болгария", 200),
]

SYSTEM_PROMPT = (
    "Ты — ассистент по недвижимости в Болгарии. Отвечай кратко и по делу на русском языке."
)

REWRITE_PROMPT = (
    "Ты — помощник по поиску недвижимости. "
    "Переформулируй запрос для поиска по базе. "
    "Верни ТОЛЬКО переформулированный запрос."
)


async def _call_sdk_router(
    *,
    model: str,
    query: str,
    max_tokens: int,
    system: str = SYSTEM_PROMPT,
) -> dict:
    """Single SDK-router LLM call with timing."""
    client = create_llm_client(model=model, timeout=120.0)
    t0 = time.perf_counter()
    try:
        resp = await client.completion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
        )
    except TimeoutError:
        return {"error": "TIMEOUT", "latency": time.perf_counter() - t0}
    except Exception as exc:
        return {"error": str(exc), "latency": time.perf_counter() - t0}

    elapsed = time.perf_counter() - t0
    usage = getattr(resp, "usage", None)
    out_tok = getattr(usage, "completion_tokens", 0) or 0
    prompt_tok = getattr(usage, "prompt_tokens", 0) or 0
    choice = (getattr(resp, "choices", None) or [None])[0]
    message = getattr(choice, "message", None) if choice is not None else None
    content = getattr(message, "content", "") or ""
    return {
        "latency": round(elapsed, 3),
        "output_tokens": out_tok,
        "input_tokens": prompt_tok,
        "tok_per_sec": round(out_tok / elapsed, 1) if elapsed > 0 else 0,
        "content_len": len(content),
        "content_preview": content[:80].replace("\n", " "),
    }


async def _call_http(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    max_tokens: int,
    system: str = SYSTEM_PROMPT,
) -> dict:
    """Single direct OpenAI-compatible HTTP call with timing."""
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120.0,
        )
    except httpx.TimeoutException:
        return {"error": "TIMEOUT", "latency": time.perf_counter() - t0}

    elapsed = time.perf_counter() - t0
    data = resp.json()
    if resp.status_code != 200:
        msg = data.get("error", {}).get("message", str(resp.status_code))
        return {"error": msg, "latency": elapsed}

    usage = data.get("usage", {})
    out_tok = usage.get("completion_tokens", 0)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    return {
        "latency": round(elapsed, 3),
        "output_tokens": out_tok,
        "input_tokens": usage.get("prompt_tokens", 0),
        "tok_per_sec": round(out_tok / elapsed, 1) if elapsed > 0 else 0,
        "content_len": len(content),
        "content_preview": content[:80].replace("\n", " "),
    }


async def run_benchmark() -> list[dict]:
    """Run all benchmarks and return results."""
    results: list[dict] = []

    configs = [
        ("sdk-router/gpt-4o-mini", "sdk", "", "gpt-4o-mini"),
        ("sdk-router/gpt-oss-120b", "sdk", "", "gpt-oss-120b"),
        ("direct/gpt-oss-120b", CEREBRAS_URL, CEREBRAS_KEY, "gpt-oss-120b"),
    ]

    async with httpx.AsyncClient() as client:
        for label, base_url, api_key, model in configs:
            if base_url != "sdk" and not api_key:
                print(f"  SKIP {label}: no API key")
                continue

            print(f"\n--- {label} ---")
            for qtype, query, max_tok in TEST_QUERIES:
                system = REWRITE_PROMPT if qtype == "rewrite" else SYSTEM_PROMPT
                print(f"  [{qtype}] {query[:35]}...", end=" ", flush=True)

                if base_url == "sdk":
                    r = await _call_sdk_router(
                        model=model,
                        query=query,
                        max_tokens=max_tok,
                        system=system,
                    )
                else:
                    r = await _call_http(
                        client,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        query=query,
                        max_tokens=max_tok,
                        system=system,
                    )
                r["label"] = label
                r["query"] = query[:40]
                r["type"] = qtype
                results.append(r)

                if "error" in r:
                    print(f"ERROR: {r['error']}")
                else:
                    print(f"{r['latency']}s  {r['tok_per_sec']} tok/s  {r['output_tokens']} tok")

    return results


def print_summary(results: list[dict]) -> None:
    """Print formatted summary table."""
    print("\n" + "=" * 110)
    print(
        f"{'Label':<25} {'Type':<8} {'Query':<30} {'Lat':>6} {'OutTok':>7} {'tok/s':>7} {'Len':>5}"
    )
    print("-" * 110)

    for r in results:
        if "error" in r:
            print(f"{r['label']:<25} {r['type']:<8} {r['query']:<30} {'ERR':>6} {r['error']}")
        else:
            print(
                f"{r['label']:<25} {r['type']:<8} {r['query']:<30} "
                f"{r['latency']:>5.1f}s {r['output_tokens']:>7} "
                f"{r['tok_per_sec']:>6.0f} {r['content_len']:>5}"
            )

    # Агрегаты по label + type
    print("\n" + "=" * 70)
    print("AGGREGATE (по label × type):")
    labels = sorted({r["label"] for r in results})
    for label in labels:
        for qtype in ("generate", "rewrite"):
            group = [
                r
                for r in results
                if r["label"] == label and r["type"] == qtype and "error" not in r
            ]
            if not group:
                continue
            lats = sorted(r["latency"] for r in group)
            tps = [r["tok_per_sec"] for r in group]
            n = len(lats)
            print(
                f"  {label} [{qtype}]:  "
                f"n={n}  avg={sum(lats) / n:.1f}s  "
                f"p50={lats[n // 2]:.1f}s  max={max(lats):.1f}s  "
                f"avg_tps={sum(tps) / n:.0f}"
            )


def save_results(results: list[dict]) -> str:
    """Save results to JSON."""
    Path("logs").mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = f"logs/benchmark-llm-{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return path


def main() -> None:
    print("LLM Benchmark: gpt-4o-mini (SDK router) vs gpt-oss-120b (Cerebras)")
    print("LiteLLM SDK router: in-process")
    print(f"Direct:  {CEREBRAS_URL}")
    print(
        f"Queries: {len(TEST_QUERIES)} "
        f"({sum(1 for q in TEST_QUERIES if q[0] == 'generate')} generate "
        f"+ {sum(1 for q in TEST_QUERIES if q[0] == 'rewrite')} rewrite)"
    )

    results = asyncio.run(run_benchmark())
    print_summary(results)

    path = save_results(results)
    print(f"\nResults saved to: {path}")


if __name__ == "__main__":
    main()
