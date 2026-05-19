"""Claude-based contextualization provider."""

from typing import Any, cast

from anthropic import Anthropic, APIStatusError, AsyncAnthropic, RateLimitError
from langfuse import observe
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import BaseContextualizationProvider, ContextualizedChunk


def _extract_claude_text(content_blocks: Any) -> str:
    """Extract plain text from Anthropic content blocks."""
    parts: list[str] = []
    for block in content_blocks:
        block_text = getattr(block, "text", None)
        if isinstance(block_text, str):
            parts.append(block_text)
    return "".join(parts)


class ClaudeContextualizer(BaseContextualizationProvider):
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

    context_method = "claude"

    # Rough cost estimation: $5/MTok input, $15/MTok output
    cost_per_input_token: float = 5 / 1_000_000
    cost_per_output_token: float = 15 / 1_000_000

    def __init__(self, settings: Settings | None = None, use_cache: bool = True) -> None:
        """Initialize Claude contextualizer.

        Args:
            settings: Configuration settings (uses global if None)
            use_cache: Enable prompt caching for cost reduction
        """
        super().__init__()
        self.settings = settings or Settings()
        self.use_cache = use_cache
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.sync_client = Anthropic(api_key=self.settings.anthropic_api_key)

    @observe(name="claude-contextualize-batch", capture_input=False, capture_output=False)
    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks using Claude."""
        return await super().contextualize(chunks, query, context_window)

    @observe(name="claude-contextualize", capture_input=False, capture_output=False)
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
        """Contextualize a single chunk using Claude (with retry)."""
        return await super().contextualize_single(text, article_number, query)

    async def _call_llm_async(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute Claude API call with optional prompt caching."""
        model_name = self.settings.model_name or "claude-3-5-haiku-latest"

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
        text = _extract_claude_text(response.content)
        return text, response.usage.input_tokens, response.usage.output_tokens

    @observe(name="claude-contextualize-sync", capture_input=False, capture_output=False)
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
        return super().contextualize_sync(text, article_number, query)

    def _call_llm_sync(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute sync Claude API call."""
        model_name = self.settings.model_name or "claude-3-5-haiku-latest"
        response = self.sync_client.messages.create(
            model=model_name,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = _extract_claude_text(response.content)
        return text, response.usage.input_tokens, response.usage.output_tokens

    def get_stats(self) -> dict[str, int | float]:
        """Get contextualization statistics."""
        stats = super().get_stats()
        stats["avg_cost_per_chunk"] = (
            round(self.total_cost / self.total_tokens * 1000, 4) if self.total_tokens > 0 else 0
        )
        return stats
