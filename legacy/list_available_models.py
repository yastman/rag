#!/usr/bin/env python3
"""
List available models from OpenAI and Groq
"""

import os

from dotenv import load_dotenv


load_dotenv()

print("=" * 80)
print("AVAILABLE MODELS")
print("=" * 80)

# OpenAI
print("\n🤖 OpenAI Models:")
try:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    models = client.models.list()
    openai_models = [
        m.id
        for m in models.data
        if "gpt" in m.id.lower() or "o1" in m.id.lower() or "o3" in m.id.lower()
    ]

    for model in sorted(openai_models):
        print(f"  - {model}")

except Exception as e:
    print(f"  ❌ Error: {e}")

# Groq
print("\n⚡ Groq Models:")
try:
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    models = client.models.list()

    for model in models.data:
        print(
            f"  - {model.id} (context: {model.context_window if hasattr(model, 'context_window') else 'N/A'})"
        )

except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
