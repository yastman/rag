"""Groq-based contextualization provider (high-speed alternative)."""

from groq import APIStatusError, AsyncGroq, Groq, RateLimitError
from langfuse import observe
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import BaseContextualizationProvider, ContextualizedChunk


def _usage_counts(usage: object | None) -> tuple[int, int]:
    """Return prompt/completion counts, falling back to total_tokens-only SDK mocks."""
    if usage is None:
        return 0, 0
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if isinstance(prompt, int) or isinstance(completion, int):
        return int(prompt or 0), int(completion or 0)
    total = getattr(usage, "total_tokens", None)
    return (int(total), 0) if isinstance(total, int) else (0, 0)


class GroqContextualizer(BaseContextualizationProvider):
    """
    Contextualize documents using Groq API (high-speed).

    Performance:
    - ~2-4 minutes for 100 chunks (fastest)
    - Cost: Free (Groq's free tier for LLaMA)
    - Quality: Good (uses LLaMA 3)

    Note: Fast inference on LLaMA, trade-off with quality.
    """

    context_method = "groq"

    # Groq free tier — no cost
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Groq contextualizer."""
        super().__init__()
        self.settings = settings or Settings()
        self.client = AsyncGroq(api_key=self.settings.groq_api_key)
        self.sync_client = Groq(api_key=self.settings.groq_api_key)

    @observe(name="groq-contextualize-batch", capture_input=False, capture_output=False)
    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks using Groq."""
        return await super().contextualize(chunks, query, context_window)

    @observe(name="groq-contextualize", capture_input=False, capture_output=False)
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
        """Contextualize a single chunk using Groq (with retry)."""
        return await super().contextualize_single(text, article_number, query)

    async def _call_llm_async(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute Groq API call."""
        response = await self.client.chat.completions.create(
            model="llama3-70b-8192",
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        usage = getattr(response, "usage", None)
        prompt_tokens, completion_tokens = _usage_counts(usage)
        return response.choices[0].message.content or "", prompt_tokens, completion_tokens

    @observe(name="groq-contextualize-sync", capture_input=False, capture_output=False)
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
        """Synchronous contextualization using Groq."""
        return super().contextualize_sync(text, article_number, query)

    def _call_llm_sync(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute sync Groq API call."""
        response = self.sync_client.chat.completions.create(
            model="llama3-70b-8192",
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        usage = getattr(response, "usage", None)
        prompt_tokens, completion_tokens = _usage_counts(usage)
        return response.choices[0].message.content or "", prompt_tokens, completion_tokens

    def get_stats(self) -> dict[str, int | float]:
        """Get contextualization statistics (Groq is free)."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": 0.0,
        }
