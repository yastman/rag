#!/usr/bin/env python3
"""Test OpenAI API connection."""

import asyncio

import httpx


async def test_openai():
    """Test OpenAI API."""
    api_key = "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"

    print("Testing OpenAI API connection...")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Скажи привет на русском"}],
                    "max_tokens": 50,
                },
            )

            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                print("✅ OpenAI API works!")
                print(f"Response: {answer}")
                return True
            print(f"❌ Error {response.status_code}: {response.text}")
            return False

        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False


if __name__ == "__main__":
    asyncio.run(test_openai())
