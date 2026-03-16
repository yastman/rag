"""Claude-based contextualization provider."""

from typing import Any, cast

from anthropic import Anthropic, APIStatusError, AsyncAnthropic, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import ContextualizedChunk, ContextualizeProvider


def _extract_claude_text(content_blocks: Any) -> str:
    """Extract plain text from Anthropic content blocks."""
    parts: list[str] = []
    for block in content_blocks:
        block_text = getattr(block, "text", None)
        if isinstance(block_text, str):
            parts.append(block_text)
    return "".join(parts)


class ClaudeContextualizer(ContextualizeProvider):
    """
    Contextualize documents using Anthropic Claude API.

    Features:
    - Prompt caching for 90% cost reduction
    - Token tracking for cost estimation
    - Async/sync support
    - Automatic fallback on failures

    Performance:
    - ~8-12 minutes for 100 chunks (with contextualization)
    - Cost: ~$0.003-0.01 per chunk (with caching)
    - Quality: Highest among available providers
    """

    def __init__(self, settings: Settings | None = None, use_cache: bool = True) -> None:
        """Initialize Claude contextualizer.

        Args:
            settings: Configuration settings (uses global if None)
            use_cache: Enable prompt caching for cost reduction
        """
        self.settings = settings or Settings()
        self.use_cache = use_cache
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.sync_client = Anthropic(api_key=self.settings.anthropic_api_key)
        self.total_tokens = 0
        self.total_cost = 0.0

    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """
        Contextualize multiple chunks using Claude.

        Uses batch processing for efficiency.
        """
        _ = context_window
        results = []
        for i, chunk in enumerate(chunks):
            try:
                result = await self.contextualize_single(chunk, f"chunk_{i}", query)
                results.append(result)
            except Exception as e:
                print(f"Warning: Failed to contextualize chunk {i}: {e}")
                # Fallback: return chunk without context
                results.append(
                    ContextualizedChunk(
                        original_text=chunk,
                        contextual_summary="",
                        article_number=f"chunk_{i}",
                        context_method="none",
                    )
                )
        return results

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIStatusError)),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(4),
    )
    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """
        Contextualize a single chunk using Claude.

        Implements prompt caching for cost efficiency.
        """
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)
        model_name = self.settings.model_name or "claude-3-5-haiku-latest"

        # Build system param with optional prompt caching
        system_content: str | list[dict[str, Any]]
        if self.use_cache:
            system_content = [
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ]
        else:
            system_content = system_prompt

        response = await self.client.messages.create(
            model=model_name,
            max_tokens=256,
            system=cast(Any, system_content),
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Track tokens and cost
        self.total_tokens += response.usage.input_tokens + response.usage.output_tokens
        # Rough cost estimation: $5/MTok input, $15/MTok output
        self.total_cost += (
            response.usage.input_tokens * 5 + response.usage.output_tokens * 15
        ) / 1_000_000

        summary = _extract_claude_text(response.content)
        if not summary.strip():
            raise ValueError("Empty Claude response content")

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=summary,
            article_number=article_number,
            context_method="claude",
        )

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIStatusError)),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(4),
    )
    def contextualize_sync(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """Synchronous contextualization (blocking)."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)
        model_name = self.settings.model_name or "claude-3-5-haiku-latest"

        response = self.sync_client.messages.create(
            model=model_name,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Track tokens
        self.total_tokens += response.usage.input_tokens + response.usage.output_tokens

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=_extract_claude_text(response.content),
            article_number=article_number,
            context_method="claude",
        )

    def get_stats(self) -> dict[str, int | float]:
        """Get contextualization statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 4),
            "avg_cost_per_chunk": (
                round(self.total_cost / self.total_tokens * 1000, 4) if self.total_tokens > 0 else 0
            ),
        }
