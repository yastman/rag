#!/usr/bin/env python3
"""
Async Contextualization Module - Groq API
Uses Groq's ultra-fast inference platform (Llama, Gemma, etc.)
"""

import asyncio
import json
import os
import re
from typing import Optional

import aiohttp
from prompts import format_enhanced_chunk_context


class ContextualRetrievalGroqAsync:
    """
    Groq async contextualizer with:
    - NO document context (optimized like Z.AI version)
    - Async parallel processing with aiohttp
    - Semaphore for rate limiting
    - Support for Llama, Gemma, and other Groq models
    - Ultra-fast inference (up to 1000 TPS)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.1-8b-instant",  # Default: fast and cheap
        max_tokens: int = 1500,
        temperature: float = 0.0,
        max_retries: int = 3,
        rate_limit_delay: float = 0.5,
        max_concurrent: int = 10,
    ):
        """
        Initialize Groq async contextualizer.

        Args:
            api_key: Groq API key
            model: Groq model (llama-3.1-8b-instant, gemma2-9b-it, etc.)
            max_tokens: Max response tokens
            temperature: 0.0 for deterministic
            max_retries: Retry attempts
            rate_limit_delay: Delay between requests
            max_concurrent: Max parallel requests
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found")

        ***REMOVED*** endpoint (OpenAI-compatible)
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
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
            "total_cost_usd": 0.0,
            "total_time_seconds": 0.0,
        }

        # Pricing (per 1M tokens) - as of 2025-10-22
        self.pricing = {
            # Budget tier
            "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
            "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
            # Mid tier
            "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.11, "output": 0.34},
            "qwen/qwen3-32b": {"input": 0.29, "output": 0.59},
            "gemma2-9b-it": {"input": 0.20, "output": 0.20},
            # Premium tier
            "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
            "meta-llama/llama-4-maverick-17b-128e-instruct": {"input": 0.20, "output": 0.60},
            "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
            "moonshotai/kimi-k2-instruct": {"input": 1.00, "output": 3.00},
        }

    async def situate_context_with_metadata(
        self, chunk_text: str, document_name: str = "Цивільний кодекс України"
    ) -> tuple[str, dict]:
        """
        Generate context WITHOUT full document (OPTIMIZATION!)

        Args:
            chunk_text: Chunk to contextualize (NO doc_content!)
            document_name: Document name

        Returns:
            (context_text, metadata_dict)
        """
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
                    }

                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    }

                    # Async HTTP request
                    start_time = asyncio.get_event_loop().time()
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
                    end_time = asyncio.get_event_loop().time()

                    # Track request time
                    request_time = end_time - start_time
                    self.stats["total_time_seconds"] += request_time

                    # Update stats
                    self.stats["total_calls"] += 1
                    self.stats["successful_calls"] += 1

                    # Track tokens and cost
                    if "usage" in result:
                        usage = result["usage"]
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)

                        self.stats["total_input_tokens"] += input_tokens
                        self.stats["total_output_tokens"] += output_tokens

                        # Calculate cost
                        if self.model in self.pricing:
                            cost = (
                                input_tokens / 1_000_000 * self.pricing[self.model]["input"]
                                + output_tokens / 1_000_000 * self.pricing[self.model]["output"]
                            )
                            self.stats["total_cost_usd"] += cost

                    # Parse response
                    message = result["choices"][0]["message"]
                    response_text = message.get("content", "")

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
                        print(f"ERROR: Groq API failed after {self.max_retries} attempts: {e}")
                        return self._fallback_extraction(chunk_text)
                    wait_time = 2**attempt
                    print(
                        f"WARNING: Groq API error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)

        return self._fallback_extraction(chunk_text)

    def _parse_response(self, response_text: str, chunk_text: str) -> tuple[str, dict]:
        """Parse Groq response."""
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
            stats["avg_time_per_call"] = stats["total_time_seconds"] / stats["total_calls"]
        else:
            stats["success_rate"] = 0.0
            stats["avg_time_per_call"] = 0.0
        return stats

    def print_stats(self):
        """Print statistics."""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("CONTEXTUAL RETRIEVAL (Groq ASYNC) - USAGE STATISTICS")
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
        print("Performance:")
        print(f"  Total Time: {stats['total_time_seconds']:.2f}s")
        if stats["total_calls"] > 0:
            print(f"  Avg Time/Call: {stats['avg_time_per_call']:.3f}s")
            tps = (stats["total_input_tokens"] + stats["total_output_tokens"]) / stats[
                "total_time_seconds"
            ]
            print(f"  Tokens/Second: {tps:.0f} TPS")
        print()
        print("Cost (USD):")
        print(f"  Total: ${stats['total_cost_usd']:.4f}")
        if stats["total_calls"] > 0:
            print(f"  Per Call: ${stats['total_cost_usd'] / stats['total_calls']:.6f}")
        print()
        print("OPTIMIZATION: NO document context sent (saves ~8,750 tokens/request)")
        print("=" * 80 + "\n")
