#!/usr/bin/env python3
"""
List available models from OpenAI and Groq using REST API
"""

import asyncio
import os

import aiohttp
from dotenv import load_dotenv


load_dotenv()


async def list_openai_models():
    """List OpenAI models."""
    print("\n🤖 OpenAI Models:")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("  ❌ OPENAI_API_KEY not set")
        return []

    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response,
        ):
            if response.status == 200:
                data = await response.json()
                models = [
                    m["id"]
                    for m in data["data"]
                    if "gpt" in m["id"].lower() or "o1" in m["id"] or "o3" in m["id"]
                ]

                for model in sorted(models):
                    print(f"  - {model}")

                return models
            print(f"  ❌ Error: {response.status}")
            return []

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return []


async def list_groq_models():
    """List Groq models."""
    print("\n⚡ Groq Models:")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("  ❌ GROQ_API_KEY not set")
        return []

    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response,
        ):
            if response.status == 200:
                data = await response.json()

                models = []
                for m in data["data"]:
                    model_id = m["id"]
                    context = m.get("context_window", "N/A")
                    print(f"  - {model_id} (context: {context})")
                    models.append(model_id)

                return models
            print(f"  ❌ Error: {response.status}")
            text = await response.text()
            print(f"     {text[:200]}")
            return []

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return []


async def main():
    print("=" * 80)
    print("AVAILABLE MODELS")
    print("=" * 80)

    openai_models = await list_openai_models()
    groq_models = await list_groq_models()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"OpenAI: {len(openai_models)} models")
    print(f"Groq: {len(groq_models)} models")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
