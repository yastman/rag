"""Groq-based contextualization provider (high-speed alternative)."""

from groq import APIStatusError, AsyncGroq, Groq, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import ContextualizedChunk, ContextualizeProvider


class GroqContextualizer(ContextualizeProvider):
    """
    Contextualize documents using Groq API (high-speed).

    Performance:
    - ~2-4 minutes for 100 chunks (fastest)
    - Cost: Free (Groq's free tier for LLaMA)
    - Quality: Good (uses LLaMA 3)

    Note: Fast inference on LLaMA, trade-off with quality.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Groq contextualizer."""
        self.settings = settings or Settings()
        self.client = AsyncGroq(api_key=self.settings.groq_api_key)
        self.sync_client = Groq(api_key=self.settings.groq_api_key)
        self.total_tokens = 0

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
        """Contextualize a single chunk using Groq."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)

        response = await self.client.chat.completions.create(
            model="llama3-70b-8192",  # Groq's default fast model
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        # Track tokens
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.total_tokens += int(usage.total_tokens or 0)

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content or "",
            article_number=article_number,
            context_method="groq",
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
        """Synchronous contextualization using Groq."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)

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
        if usage is not None:
            self.total_tokens += int(usage.total_tokens or 0)

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content or "",
            article_number=article_number,
            context_method="groq",
        )

    def get_stats(self) -> dict[str, int | float]:
        """Get contextualization statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": 0.0,  # Groq is free
        }
