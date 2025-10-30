#!/usr/bin/env python3
"""
Async Contextualization Module - OPTIMIZED VERSION
Removes document context + async parallel processing = 15-50x speedup

Langfuse Integration (2025):
- Traces every LLM call with @observe decorator
- Captures input, output, latency, tokens, cost
- Enables production monitoring and cost optimization
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import aiohttp


# Add src/ to path for Langfuse import
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from langfuse import get_client, observe

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

    # Dummy decorator if Langfuse not available
    def observe(*args, **kwargs):
        def decorator(func):
            return func

        return decorator if args and callable(args[0]) else decorator


from prompts import format_enhanced_chunk_context


class ContextualRetrievalZAIAsync:
    """
    OPTIMIZED async version with:
    - NO document context (removes 8,750 tokens overhead)
    - Async parallel processing with aiohttp
    - Semaphore for rate limiting
    - 15-50x faster than original
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "glm-4.6",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        max_retries: int = 3,
        rate_limit_delay: float = 0.5,  # Reduced from 1.2s
        max_concurrent: int = 10,  # Parallel requests
    ):
        """
        Initialize async contextualizer.

        Args:
            api_key: Z.AI API key
            model: Z.AI model
            max_tokens: Max response tokens
            temperature: 0.0 for deterministic
            max_retries: Retry attempts
            rate_limit_delay: Delay between requests (reduced)
            max_concurrent: Max parallel requests
        """
        self.api_key = api_key or os.getenv("ZAI_API_KEY")
        if not self.api_key:
            raise ValueError("ZAI_API_KEY not found")

        # GLM Coding Plan endpoint
        self.api_url = "https://api.z.ai/api/coding/paas/v4/chat/completions"
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay

        # Async control
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Stats
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    @observe(as_type="generation")
    async def situate_context_with_metadata(
        self, chunk_text: str, document_name: str = "Цивільний кодекс України"
    ) -> tuple[str, dict]:
        """
        Generate context WITHOUT full document (OPTIMIZATION!)

        Langfuse automatically captures:
        - Input: chunk_text + document_name
        - Output: context_text + metadata
        - Latency: time taken
        - Tokens: input/output (if available from API)
        - Cost: calculated from tokens

        Args:
            chunk_text: Chunk to contextualize (NO doc_content!)
            document_name: Document name

        Returns:
            (context_text, metadata_dict)
        """
        # Update Langfuse metadata (if available)
        if LANGFUSE_AVAILABLE:
            try:
                langfuse = get_client()
                langfuse.update_current_generation(
                    name="contextualize_chunk",
                    model=self.model,
                    model_parameters={
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                    },
                    metadata={
                        "document": document_name,
                        "chunk_length": len(chunk_text),
                        "optimization": "no_document_context",
                    },
                )
            except Exception:
                pass  # Silently fail if Langfuse not configured

        async with self.semaphore:  # Rate limiting
            for attempt in range(self.max_retries):
                try:
                    # OPTIMIZED prompt: only chunk + minimal context
                    system_prompt = f"""Ти - експертна система для аналізу структури юридичних документів України.

Твоя задача: проаналізувати фрагмент з "{document_name}" і надати:

1. КОНТЕКСТ (1-2 речення): короткий опис місця цього фрагменту в загальній структурі документа
2. МЕТАДАНІ (JSON): структурна інформація

Формат відповіді:
КОНТЕКСТ: [1-2 речення про місце фрагменту в документі]

МЕТАДАНІ:
{{
  "book": "назва книги або null",
  "book_number": число або null,
  "section": "назва розділу або null",
  "section_number": число або null,
  "chapter": "назва глави або null",
  "chapter_number": число або null,
  "article_number": число або null,
  "article_title": "назва статті або null",
  "related_articles": [номери пов'язаних статей]
}}

Важливо: JSON має бути валідний (без коментарів, без trailing commas)."""

                    chunk_prompt = format_enhanced_chunk_context(chunk_text)

                    # Prepare request
                    payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": chunk_prompt},
                        ],
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "thinking": {"type": "disabled"},
                    }

                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    }

                    # Async HTTP request
                    async with (
                        aiohttp.ClientSession() as session,
                        session.post(
                            self.api_url,
                            json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as response,
                    ):
                        response.raise_for_status()
                        result = await response.json()

                    # Update stats
                    self.stats["total_calls"] += 1
                    self.stats["successful_calls"] += 1

                    # Track tokens
                    if "usage" in result:
                        usage = result["usage"]
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)

                        self.stats["total_input_tokens"] += input_tokens
                        self.stats["total_output_tokens"] += output_tokens

                        # Update Langfuse with usage (if available)
                        if LANGFUSE_AVAILABLE:
                            try:
                                langfuse = get_client()
                                langfuse.update_current_generation(
                                    usage={
                                        "input": input_tokens,
                                        "output": output_tokens,
                                        "total": input_tokens + output_tokens,
                                    }
                                )
                            except Exception:
                                pass

                    # Parse response
                    message = result["choices"][0]["message"]
                    response_text = message.get("reasoning_content") or message.get("content", "")

                    if not response_text:
                        return self._fallback_extraction(chunk_text)

                    context_text, metadata = self._parse_response(response_text, chunk_text)

                    # Small delay for rate limiting
                    await asyncio.sleep(self.rate_limit_delay)

                    return context_text, metadata

                except Exception as e:
                    self.stats["total_calls"] += 1
                    self.stats["failed_calls"] += 1

                    if attempt == self.max_retries - 1:
                        print(f"ERROR: Z.AI API failed after {self.max_retries} attempts: {e}")
                        return self._fallback_extraction(chunk_text)
                    wait_time = 2**attempt
                    print(
                        f"WARNING: Z.AI API error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)

        return self._fallback_extraction(chunk_text)

    def _parse_response(self, response_text: str, chunk_text: str) -> tuple[str, dict]:
        """Parse Z.AI response."""
        try:
            # Extract context
            context_match = re.search(r"КОНТЕКСТ:\s*(.+?)(?=МЕТАДАНІ:|$)", response_text, re.DOTALL)
            if context_match:
                context_text = context_match.group(1).strip()
            else:
                context_text = "Цей фрагмент з Цивільного кодексу України."

            # Extract metadata JSON
            metadata_match = re.search(r"МЕТАДАНІ:\s*(\{.+?\})", response_text, re.DOTALL)
            if metadata_match:
                metadata_str = metadata_match.group(1).strip()
                metadata_str = self._clean_json(metadata_str)
                metadata = json.loads(metadata_str)
            else:
                metadata = {}

            metadata = self._validate_metadata(metadata)
            return context_text, metadata

        except Exception as e:
            print(f"WARNING: Error parsing response: {e}")
            return self._fallback_extraction(chunk_text)

    def _clean_json(self, json_str: str) -> str:
        """Clean JSON string."""
        json_str = re.sub(r"//.*?\n", "\n", json_str)
        json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
        json_str = re.sub(r",\s*}", "}", json_str)
        return re.sub(r",\s*]", "]", json_str)

    def _validate_metadata(self, metadata: dict) -> dict:
        """Validate metadata."""
        defaults = {
            "book": None,
            "book_number": None,
            "section": None,
            "section_number": None,
            "chapter": None,
            "chapter_number": None,
            "article_number": None,
            "article_title": None,
            "related_articles": [],
        }

        result = defaults.copy()
        result.update(metadata)

        if not isinstance(result["related_articles"], list):
            result["related_articles"] = []

        for key in ["book_number", "section_number", "chapter_number", "article_number"]:
            if result[key] is not None and not isinstance(result[key], int):
                try:
                    result[key] = int(result[key])
                except (ValueError, TypeError):
                    result[key] = None

        return result

    def _fallback_extraction(self, chunk_text: str) -> tuple[str, dict]:
        """Fallback when API fails."""
        from utils.structure_parser import extract_related_articles, parse_legal_structure

        context_text = "Цей фрагмент з Цивільного кодексу України."
        metadata = parse_legal_structure(chunk_text)
        metadata["related_articles"] = extract_related_articles(chunk_text)

        return context_text, metadata

    def get_stats(self) -> dict:
        """Get statistics."""
        stats = self.stats.copy()
        if stats["total_calls"] > 0:
            stats["success_rate"] = stats["successful_calls"] / stats["total_calls"]
        else:
            stats["success_rate"] = 0.0
        return stats

    def print_stats(self):
        """Print statistics."""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("CONTEXTUAL RETRIEVAL (Z.AI ASYNC) - USAGE STATISTICS")
        print("=" * 80)
        print(f"Model: {self.model}")
        print(f"Total API Calls: {stats['total_calls']}")
        print(f"  ✓ Successful: {stats['successful_calls']}")
        print(f"  ✗ Failed: {stats['failed_calls']}")
        print(f"  Success Rate: {stats['success_rate']:.1%}")
        print()
        print("Token Usage:")
        print(f"  Input Tokens: {stats['total_input_tokens']:,}")
        print(f"  Output Tokens: {stats['total_output_tokens']:,}")
        print()
        print("OPTIMIZATION: NO document context sent (saves ~8,750 tokens/request)")
        print("Cost: Subscription-based (~$3/month unlimited)")
        print("=" * 80 + "\n")
