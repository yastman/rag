"""Claude-based contextualization provider."""

from typing import Any, cast

from anthropic import Anthropic, APIStatusError, AsyncAnthropic, RateLimitError
from langfuse import observe
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import ContextualizedChunk, ContextualizeProvider


# Claude pricing — USD per 1M tokens. Per-model rates are application-level
# concerns (the SDK does not surface pricing); centralized here so the shared
# cost helper in base.py drives the math (issue #1234).
_CLAUDE_INPUT_PRICE_PER_MTOK = 5.0
_CLAUDE_OUTPUT_PRICE_PER_MTOK = 15.0


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
    - Token tracking for cost estimation (cache-aware after #1234)
    - Async/sync support
    - Automatic fallback on failures

    Performance:
    - ~8-12 minutes for 100 chunks (with contextualization)
    - Cost: ~$0.003-0.01 per chunk (with caching)
    - Quality: Highest among available providers
    """

    def __init__(
        self,
        settings: Settings | None = None,
        use_cache: bool = True,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize Claude contextualizer.

        Args:
            settings: Configuration settings (uses global if None)
            use_cache: Enable prompt caching for cost reduction
            system_prompt: Optional custom contextualization system prompt
        """
        super().__init__(system_prompt=system_prompt)
        self.settings = settings or Settings()
        self.use_cache = use_cache
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.sync_client = Anthropic(api_key=self.settings.anthropic_api_key)
        self.total_tokens = 0
        self.total_cost = 0.0

    @observe(name="claude-contextualize-batch", capture_input=False, capture_output=False)
    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks using Claude.

        Thin delegate to ``ContextualizeProvider.contextualize_batch`` (#1533),
        which provides the shared concurrent per-chunk dispatch (TaskGroup +
        semaphore) with per-chunk fallback to ``context_method="none"``. The
        ``@observe`` span name keeps provider-specific tracing intact.
        """
        _ = context_window
        return await self.contextualize_batch(chunks, query)

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
        """
        Contextualize a single chunk using Claude.

        Implements prompt caching for cost efficiency. Token + cost
        accounting honours Anthropic's SDK contract that
        ``Total input tokens = input_tokens + cache_creation_input_tokens
        + cache_read_input_tokens`` (issue #1234).
        """
        system_prompt = self.system_prompt
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

        # SDK-correct accounting (issue #1234):
        #   Total input = input + cache_creation_input + cache_read_input
        # The previous code summed only input_tokens + output_tokens which
        # silently undercounted whenever prompt caching was active.
        usage = response.usage
        total_input_tokens = self._total_input_tokens_from_anthropic_usage(usage)
        output_tokens = self._coerce_token_count(getattr(usage, "output_tokens", 0))
        cache_creation_tokens = self._coerce_token_count(
            getattr(usage, "cache_creation_input_tokens", 0)
        )
        cache_read_tokens = self._coerce_token_count(getattr(usage, "cache_read_input_tokens", 0))
        regular_input_tokens = self._coerce_token_count(getattr(usage, "input_tokens", 0))

        self.total_tokens += total_input_tokens + output_tokens
        self.total_cost += self._calculate_token_cost(
            input_tokens=regular_input_tokens,
            output_tokens=output_tokens,
            input_price_per_mtok=_CLAUDE_INPUT_PRICE_PER_MTOK,
            output_price_per_mtok=_CLAUDE_OUTPUT_PRICE_PER_MTOK,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
        )

        summary = _extract_claude_text(response.content)
        if not summary.strip():
            raise ValueError("Empty Claude response content")

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=summary,
            article_number=article_number,
            context_method="claude",
        )

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
        system_prompt = self.system_prompt
        user_prompt = self.get_user_prompt(text, query)
        model_name = self.settings.model_name or "claude-3-5-haiku-latest"

        response = self.sync_client.messages.create(
            model=model_name,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # SDK-correct accounting (issue #1234) — also covers the sync path.
        usage = response.usage
        total_input_tokens = self._total_input_tokens_from_anthropic_usage(usage)
        output_tokens = self._coerce_token_count(getattr(usage, "output_tokens", 0))
        self.total_tokens += total_input_tokens + output_tokens

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
