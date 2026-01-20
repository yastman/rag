#!/usr/bin/env python3
"""
Contextualization Module for RAG Pipeline - Z.AI Version
Uses Z.AI GLM-4.6 API for context generation
"""

import json
import os
import re
import time
from typing import Optional

import requests
from prompts import (
    DOCUMENT_CONTEXT_PROMPT,
    format_enhanced_chunk_context,
)


class ContextualRetrievalZAI:
    """
    Implements Contextual Retrieval using Z.AI GLM-4.6 API.

    Features:
    - Z.AI GLM-4.6 integration (OpenAI-compatible API)
    - Context + metadata + relationships extraction
    - Retry logic with exponential backoff
    - Comprehensive error handling
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "glm-4.6",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        max_retries: int = 3,
        rate_limit_delay: float = 1.2,
    ):
        """
        Initialize the ContextualRetrievalZAI module.

        Args:
            api_key: Z.AI API key
            model: Z.AI model to use (glm-4.6 recommended)
            max_tokens: Maximum tokens for response
            temperature: 0.0 for deterministic output
            max_retries: Number of retry attempts on failure
            rate_limit_delay: Delay between API calls (seconds)
        """
        self.api_key = api_key or os.getenv("ZAI_API_KEY")
        if not self.api_key:
            raise ValueError("ZAI_API_KEY not found. Set it in environment or pass to constructor.")

        # For GLM Coding Plan subscribers, use the coding endpoint
        self.api_url = "https://api.z.ai/api/coding/paas/v4/chat/completions"
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay

        # Stats tracking
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    def situate_context_with_metadata(
        self, doc_content: str, chunk_text: str, document_name: str = "Цивільний кодекс України"
    ) -> tuple[str, dict]:
        """
        Generate contextual prefix and extract metadata using Z.AI API.

        Args:
            doc_content: Full document text
            chunk_text: Individual chunk to contextualize
            document_name: Name of the document

        Returns:
            Tuple of (context_text, metadata_dict)
        """
        for attempt in range(self.max_retries):
            try:
                # Format prompts
                doc_prompt = DOCUMENT_CONTEXT_PROMPT.format(
                    document_name=document_name, doc_content=doc_content
                )
                chunk_prompt = format_enhanced_chunk_context(chunk_text)

                # Prepare Z.AI API request (OpenAI-compatible format)
                payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ти - експертна система для аналізу структури юридичних документів України. Надавай точний контекст та структурні метадані у форматі, що був запропонований.",
                        },
                        {"role": "user", "content": f"{doc_prompt}\n\n{chunk_prompt}"},
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    # Disable thinking mode for direct output
                    "thinking": {"type": "disabled"},
                }

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }

                # Call Z.AI API
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                result = response.json()

                # Update stats
                self.stats["total_calls"] += 1
                self.stats["successful_calls"] += 1

                # Track token usage (if provided)
                if "usage" in result:
                    usage = result["usage"]
                    self.stats["total_input_tokens"] += usage.get("prompt_tokens", 0)
                    self.stats["total_output_tokens"] += usage.get("completion_tokens", 0)

                # Parse response
                # GLM-4.6 может возвращать ответ в reasoning_content или content
                message = result["choices"][0]["message"]
                response_text = message.get("reasoning_content") or message.get("content", "")

                if not response_text:
                    # Если оба поля пустые - fallback
                    print("WARNING: Empty response from Z.AI API")
                    return self._fallback_extraction(chunk_text)

                context_text, metadata = self._parse_response(response_text, chunk_text)

                # Rate limiting
                time.sleep(self.rate_limit_delay)

                return context_text, metadata

            except Exception as e:
                self.stats["total_calls"] += 1
                self.stats["failed_calls"] += 1

                if attempt == self.max_retries - 1:
                    # Last attempt failed - return fallback
                    print(f"ERROR: Z.AI API failed after {self.max_retries} attempts: {e}")
                    print("Falling back to basic metadata extraction for chunk")
                    return self._fallback_extraction(chunk_text)
                # Retry with exponential backoff
                wait_time = 2**attempt
                print(f"WARNING: Z.AI API error (attempt {attempt + 1}/{self.max_retries}): {e}")
                print(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

        # Should never reach here, but just in case
        return self._fallback_extraction(chunk_text)

    def _parse_response(self, response_text: str, chunk_text: str) -> tuple[str, dict]:
        """Parse Z.AI response to extract context and metadata."""
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

            # Validate and fill defaults
            metadata = self._validate_metadata(metadata)

            return context_text, metadata

        except json.JSONDecodeError as e:
            print(f"WARNING: Failed to parse JSON metadata: {e}")
            return self._fallback_extraction(chunk_text)
        except Exception as e:
            print(f"WARNING: Error parsing Z.AI response: {e}")
            return self._fallback_extraction(chunk_text)

    def _clean_json(self, json_str: str) -> str:
        """Clean JSON string to ensure it's valid."""
        json_str = re.sub(r"//.*?\n", "\n", json_str)
        json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
        json_str = re.sub(r",\s*}", "}", json_str)
        return re.sub(r",\s*]", "]", json_str)

    def _validate_metadata(self, metadata: dict) -> dict:
        """Validate and fill default values for metadata."""
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
        """Fallback method when Z.AI API fails."""
        from utils.structure_parser import extract_related_articles, parse_legal_structure

        context_text = "Цей фрагмент з Цивільного кодексу України."
        metadata = parse_legal_structure(chunk_text)
        metadata["related_articles"] = extract_related_articles(chunk_text)

        return context_text, metadata

    def get_stats(self) -> dict:
        """Get usage statistics."""
        stats = self.stats.copy()

        if stats["total_calls"] > 0:
            stats["success_rate"] = stats["successful_calls"] / stats["total_calls"]
        else:
            stats["success_rate"] = 0.0

        return stats

    def print_stats(self):
        """Print usage statistics."""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("CONTEXTUAL RETRIEVAL (Z.AI) - USAGE STATISTICS")
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

        # Estimate cost (Z.AI pricing: ~$3/month for unlimited GLM-4.6)
        print("Cost: Subscription-based (~$3/month unlimited)")
        print("=" * 80 + "\n")


# Example usage
if __name__ == "__main__":
    import sys

    if not os.getenv("ZAI_API_KEY"):
        print("ERROR: ZAI_API_KEY environment variable not set")
        print("Please set it before running:")
        print("  export ZAI_API_KEY='your-api-key-here'")
        sys.exit(1)

    contextualizer = ContextualRetrievalZAI()

    sample_doc = """Цивільний кодекс України
Книга перша. Загальні положення
Розділ I. Загальні положення
Глава 2. Здійснення цивільних прав та виконання обов'язків
Стаття 13. Межі здійснення цивільних прав"""

    sample_chunk = """Стаття 13. Межі здійснення цивільних прав

1. Цивільні права особа здійснює у межах, наданих їй договором або актами цивільного законодавства."""

    print("Testing Z.AI Contextual Retrieval...")
    context, metadata = contextualizer.situate_context_with_metadata(sample_doc, sample_chunk)

    print("\nRESULTS:")
    print("=" * 80)
    print("CONTEXT:", context)
    print("\nMETADATA:")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print("=" * 80)

    contextualizer.print_stats()
