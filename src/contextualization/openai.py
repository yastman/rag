"""OpenAI-based contextualization provider."""

from openai import AsyncOpenAI, OpenAI

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

    def __init__(self, settings: Settings | None = None):
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

    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """Contextualize a single chunk using OpenAI."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)

        response = await self.client.chat.completions.create(
            model=self.settings.model_name,
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        # Track tokens and cost
        usage = response.usage
        self.total_tokens += usage.total_tokens
        # OpenAI pricing: $5/MTok input (gpt-4), $15/MTok output
        self.total_cost += (usage.prompt_tokens * 5 + usage.completion_tokens * 15) / 1_000_000

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content,
            article_number=article_number,
            context_method="openai",
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

        response = self.sync_client.chat.completions.create(
            model=self.settings.model_name,
            max_tokens=256,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        usage = response.usage
        self.total_tokens += usage.total_tokens

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content,
            article_number=article_number,
            context_method="openai",
        )

    def get_stats(self) -> dict:
        """Get contextualization statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }
