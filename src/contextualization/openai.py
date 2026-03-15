"""OpenAI-based contextualization provider."""

from openai import APIStatusError, AsyncOpenAI, OpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import ContextualizedChunk, ContextualizeProvider


class OpenAIContextualizer(ContextualizeProvider):
    """
    Contextualize documents using OpenAI GPT API.

    Performance:
    - ~5-8 minutes for 100 chunks
    - Cost: ~$0.008-0.012 per chunk
    - Quality: Very good
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize OpenAI contextualizer."""
        self.settings = settings or Settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.sync_client = OpenAI(api_key=self.settings.openai_api_key)
        self.total_tokens = 0
        self.total_cost = 0.0

    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks using OpenAI."""
        _ = context_window
        results = []
        for i, chunk in enumerate(chunks):
            try:
                result = await self.contextualize_single(chunk, f"chunk_{i}", query)
                results.append(result)
            except Exception as e:
                print(f"Warning: Failed to contextualize chunk {i}: {e}")
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
        """Contextualize a single chunk using OpenAI."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)
        model_name = self.settings.model_name or "gpt-4o-mini"

        response = await self.client.chat.completions.create(
            model=model_name,
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        # Track tokens and cost
        usage = response.usage
        if usage is not None:
            total_tokens = int(usage.total_tokens or 0)
            prompt_tokens = int(usage.prompt_tokens or 0)
            completion_tokens = int(usage.completion_tokens or 0)
            self.total_tokens += total_tokens
            # OpenAI pricing: $5/MTok input (gpt-4), $15/MTok output
            self.total_cost += (prompt_tokens * 5 + completion_tokens * 15) / 1_000_000

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content or "",
            article_number=article_number,
            context_method="openai",
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
        """Synchronous contextualization using OpenAI."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)
        model_name = self.settings.model_name or "gpt-4o-mini"

        response = self.sync_client.chat.completions.create(
            model=model_name,
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        usage = response.usage
        if usage is not None:
            self.total_tokens += int(usage.total_tokens or 0)

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content or "",
            article_number=article_number,
            context_method="openai",
        )

    def get_stats(self) -> dict[str, int | float]:
        """Get contextualization statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }
