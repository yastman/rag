"""Groq-based contextualization provider (high-speed alternative)."""

from groq import AsyncGroq, Groq

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

    def __init__(self, settings: Settings | None = None):
        """Initialize Groq contextualizer."""
        self.settings = settings or Settings()
        self.client = AsyncGroq(api_key=self.settings.groq_api_key)
        self.sync_client = Groq(api_key=self.settings.groq_api_key)
        self.total_tokens = 0

    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks using Groq."""
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
        if hasattr(response, "usage"):
            self.total_tokens += response.usage.total_tokens

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content,
            article_number=article_number,
            context_method="groq",
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

        if hasattr(response, "usage"):
            self.total_tokens += response.usage.total_tokens

        return ContextualizedChunk(
            original_text=text,
            contextual_summary=response.choices[0].message.content,
            article_number=article_number,
            context_method="groq",
        )

    def get_stats(self) -> dict:
        """Get contextualization statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": 0.0,  # Groq is free
        }
