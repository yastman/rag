#!/usr/bin/env python3
"""
Contextualization Module for RAG Pipeline
Uses Claude API with prompt caching for efficient context generation
"""

import json
import os
import re
import time
from typing import Optional

from anthropic import Anthropic
from prompts import (
    DOCUMENT_CONTEXT_PROMPT,
    format_enhanced_chunk_context,
)


class ContextualRetrieval:
    """
    Implements Anthropic's Contextual Retrieval methodology for Ukrainian legal documents.

    Features:
    - Claude Haiku API integration
    - Prompt caching (90% cost reduction)
    - Context + metadata + relationships extraction in ONE call
    - Retry logic with exponential backoff
    - Comprehensive error handling
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-haiku-20240307",
        max_tokens: int = 2048,
        temperature: float = 0.0,
        max_retries: int = 3,
        rate_limit_delay: float = 1.2,
    ):
        """
        Initialize the ContextualRetrieval module.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (Haiku recommended for cost/speed)
            max_tokens: Maximum tokens for response
            temperature: 0.0 for deterministic output
            max_retries: Number of retry attempts on failure
            rate_limit_delay: Delay between API calls (seconds)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Set it in environment or pass to constructor."
            )

        self.client = Anthropic(api_key=self.api_key)
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
            "cache_hits": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_cache_read_tokens": 0,
        }

    def situate_context_with_metadata(
        self, doc_content: str, chunk_text: str, document_name: str = "Цивільний кодекс України"
    ) -> tuple[str, dict]:
        """
        Generate contextual prefix and extract metadata using Claude API.

        This is the CORE function that implements Anthropic's Contextual Retrieval.
        Uses prompt caching to reduce cost by 90%.

        Args:
            doc_content: Full document text (cached after first call)
            chunk_text: Individual chunk to contextualize
            document_name: Name of the document

        Returns:
            Tuple of (context_text, metadata_dict):
                - context_text: Contextual prefix for embedding
                - metadata_dict: Structured metadata for Qdrant payload
        """
        for attempt in range(self.max_retries):
            try:
                # Format prompts
                doc_prompt = DOCUMENT_CONTEXT_PROMPT.format(
                    document_name=document_name, doc_content=doc_content
                )
                chunk_prompt = format_enhanced_chunk_context(chunk_text)

                # Call Claude API with prompt caching (anthropic 0.71.0+)
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=[
                        {
                            "type": "text",
                            "text": doc_prompt,
                            "cache_control": {"type": "ephemeral"},  # Cache document!
                        }
                    ],
                    messages=[{"role": "user", "content": chunk_prompt}],
                )

                # Update stats
                self.stats["total_calls"] += 1
                self.stats["successful_calls"] += 1

                # Track token usage
                usage = response.usage
                self.stats["total_input_tokens"] += usage.input_tokens
                self.stats["total_output_tokens"] += usage.output_tokens

                # Track cache usage (if available)
                if hasattr(usage, "cache_creation_input_tokens"):
                    self.stats["total_cache_creation_tokens"] += usage.cache_creation_input_tokens
                if hasattr(usage, "cache_read_input_tokens"):
                    self.stats["total_cache_read_tokens"] += usage.cache_read_input_tokens
                    if usage.cache_read_input_tokens > 0:
                        self.stats["cache_hits"] += 1

                # Parse response
                response_text = response.content[0].text
                context_text, metadata = self._parse_claude_response(response_text, chunk_text)

                # Rate limiting
                time.sleep(self.rate_limit_delay)

                return context_text, metadata

            except Exception as e:
                self.stats["total_calls"] += 1
                self.stats["failed_calls"] += 1

                if attempt == self.max_retries - 1:
                    # Last attempt failed - return fallback
                    print(f"ERROR: Claude API failed after {self.max_retries} attempts: {e}")
                    print("Falling back to basic metadata extraction for chunk")
                    return self._fallback_extraction(chunk_text)
                # Retry with exponential backoff
                wait_time = 2**attempt
                print(f"WARNING: Claude API error (attempt {attempt + 1}/{self.max_retries}): {e}")
                print(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

        # Should never reach here, but just in case
        return self._fallback_extraction(chunk_text)

    def _parse_claude_response(self, response_text: str, chunk_text: str) -> tuple[str, dict]:
        """
        Parse Claude's response to extract context and metadata.

        Expected format:
        КОНТЕКСТ: [text]

        МЕТАДАНІ:
        {json}
        """
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
                # Clean up potential formatting issues
                metadata_str = self._clean_json(metadata_str)
                metadata = json.loads(metadata_str)
            else:
                metadata = {}

            # Validate and fill defaults
            metadata = self._validate_metadata(metadata)

            return context_text, metadata

        except json.JSONDecodeError as e:
            print(f"WARNING: Failed to parse JSON metadata: {e}")
            print(f"Response text: {response_text[:500]}...")
            return self._fallback_extraction(chunk_text)
        except Exception as e:
            print(f"WARNING: Error parsing Claude response: {e}")
            return self._fallback_extraction(chunk_text)

    def _clean_json(self, json_str: str) -> str:
        """Clean JSON string to ensure it's valid."""
        # Remove comments (sometimes Claude adds them despite instructions)
        json_str = re.sub(r"//.*?\n", "\n", json_str)
        json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)

        # Remove trailing commas before closing braces/brackets
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

        # Merge with defaults
        result = defaults.copy()
        result.update(metadata)

        # Ensure related_articles is a list
        if not isinstance(result["related_articles"], list):
            result["related_articles"] = []

        # Ensure numbers are integers (not strings)
        for key in ["book_number", "section_number", "chapter_number", "article_number"]:
            if result[key] is not None and not isinstance(result[key], int):
                try:
                    result[key] = int(result[key])
                except (ValueError, TypeError):
                    result[key] = None

        return result

    def _fallback_extraction(self, chunk_text: str) -> tuple[str, dict]:
        """
        Fallback method when Claude API fails.
        Uses regex-based extraction (basic, but reliable).
        """
        from utils.structure_parser import extract_related_articles, parse_legal_structure

        context_text = "Цей фрагмент з Цивільного кодексу України."
        metadata = parse_legal_structure(chunk_text)
        metadata["related_articles"] = extract_related_articles(chunk_text)

        return context_text, metadata

    def get_stats(self) -> dict:
        """Get usage statistics."""
        stats = self.stats.copy()

        # Calculate cache efficiency
        if stats["total_calls"] > 0:
            stats["cache_hit_rate"] = stats["cache_hits"] / stats["total_calls"]
            stats["success_rate"] = stats["successful_calls"] / stats["total_calls"]
        else:
            stats["cache_hit_rate"] = 0.0
            stats["success_rate"] = 0.0

        return stats

    def print_stats(self):
        """Print usage statistics in a nice format."""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("CONTEXTUAL RETRIEVAL - USAGE STATISTICS")
        print("=" * 80)
        print(f"Total API Calls: {stats['total_calls']}")
        print(f"  ✓ Successful: {stats['successful_calls']}")
        print(f"  ✗ Failed: {stats['failed_calls']}")
        print(f"  Success Rate: {stats['success_rate']:.1%}")
        print()
        print("Cache Performance:")
        print(f"  Cache Hits: {stats['cache_hits']}")
        print(f"  Cache Hit Rate: {stats['cache_hit_rate']:.1%}")
        print()
        print("Token Usage:")
        print(f"  Input Tokens: {stats['total_input_tokens']:,}")
        print(f"  Output Tokens: {stats['total_output_tokens']:,}")
        print(f"  Cache Creation Tokens: {stats['total_cache_creation_tokens']:,}")
        print(f"  Cache Read Tokens: {stats['total_cache_read_tokens']:,}")
        print()

        # Estimate cost
        if stats["total_calls"] > 0:
            # Claude Haiku pricing (as of 2024):
            # Input: $0.25/M tokens, Cached input: $0.03/M tokens, Output: $1.25/M tokens
            input_cost = (
                (stats["total_input_tokens"] - stats["total_cache_read_tokens"]) * 0.25 / 1_000_000
            )
            cache_cost = stats["total_cache_read_tokens"] * 0.03 / 1_000_000
            output_cost = stats["total_output_tokens"] * 1.25 / 1_000_000
            total_cost = input_cost + cache_cost + output_cost

            print("Estimated Cost:")
            print(f"  Input (non-cached): ${input_cost:.4f}")
            print(f"  Input (cached): ${cache_cost:.4f}")
            print(f"  Output: ${output_cost:.4f}")
            print(f"  TOTAL: ${total_cost:.4f}")

            # Calculate savings from caching
            if stats["total_cache_read_tokens"] > 0:
                without_cache_cost = (
                    stats["total_input_tokens"] * 0.25 + stats["total_output_tokens"] * 1.25
                ) / 1_000_000
                savings = without_cache_cost - total_cost
                savings_pct = (savings / without_cache_cost) * 100 if without_cache_cost > 0 else 0
                print(f"  Savings from caching: ${savings:.4f} ({savings_pct:.1f}%)")

        print("=" * 80 + "\n")


# Example usage
if __name__ == "__main__":
    # Test the module
    import sys

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        print("Please set it before running:")
        print("  export ANTHROPIC_API_KEY='your-api-key-here'")
        sys.exit(1)

    # Initialize
    contextualizer = ContextualRetrieval()

    # Test with sample text
    sample_doc = """Цивільний кодекс України

Книга перша. Загальні положення

Розділ I. Загальні положення

Глава 2. Здійснення цивільних прав та виконання обов'язків

Стаття 12. Здійснення цивільних прав

1. Особа здійснює свої цивільні права вільно, на власний розсуд.

2. Відмова особи від цивільних прав є нікчемною, крім випадків, встановлених законом.

Стаття 13. Межі здійснення цивільних прав

1. Цивільні права особа здійснює у межах, наданих їй договором або актами цивільного законодавства.

2. При здійсненні своїх прав особа зобов'язана утримуватися від дій, які могли б порушити права інших осіб, завдати шкоди довкіллю або культурній спадщині."""

    sample_chunk = """Стаття 13. Межі здійснення цивільних прав

1. Цивільні права особа здійснює у межах, наданих їй договором або актами цивільного законодавства.

2. При здійсненні своїх прав особа зобов'язана утримуватися від дій, які могли б порушити права інших осіб."""

    print("Testing Contextual Retrieval...")
    print(f"Chunk text ({len(sample_chunk)} chars):")
    print("-" * 80)
    print(sample_chunk)
    print("-" * 80)

    # Generate context
    context, metadata = contextualizer.situate_context_with_metadata(sample_doc, sample_chunk)

    print("\nRESULTS:")
    print("=" * 80)
    print("CONTEXT:")
    print(context)
    print()
    print("METADATA:")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print("=" * 80)

    # Print stats
    contextualizer.print_stats()

    print("\n✓ Test completed successfully!")
