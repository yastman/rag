"""OpenAI-based contextualization provider."""

from langfuse import observe
from langfuse.openai import AsyncOpenAI, OpenAI

from src.config import Settings

from .base import ContextualizedChunk, ContextualizeProvider


# OpenAI SDK's built-in retry policy (Context7 /openai/openai-python):
# - Default max_retries=2, exponential backoff
# - Retries: connection errors, 408 Timeout, 409 Conflict, 429 Rate Limit, >=500
# OpenAI counts max_retries after the initial request. The previous Tenacity
# stop_after_attempt(4) allowed four total attempts, so max_retries=3 preserves
# that retry budget without duplicating the policy.
_OPENAI_MAX_RETRIES = 3


class OpenAIContextualizer(ContextualizeProvider):
    """
    Contextualize documents using OpenAI GPT API.

    Performance:
    - ~5-8 minutes for 100 chunks
    - Cost: ~$0.008-0.012 per chunk
    - Quality: Very good

    Retries are handled natively by the OpenAI SDK via the ``max_retries``
    client parameter (#1651). No Tenacity decorator wraps the per-call path.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize OpenAI contextualizer."""
        self.settings = settings or Settings()
        self.client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            max_retries=_OPENAI_MAX_RETRIES,
        )
        self.sync_client = OpenAI(
            api_key=self.settings.openai_api_key,
            max_retries=_OPENAI_MAX_RETRIES,
        )
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

    @observe(name="openai-contextualize", capture_input=False, capture_output=False)
    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """Contextualize a single chunk using OpenAI.

        SDK-native retries via ``max_retries`` on the AsyncOpenAI client
        cover RateLimitError, APIStatusError (>=500), connection errors,
        408 and 409. No additional retry layer is required.
        """
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

    @observe(name="openai-contextualize-sync", capture_input=False, capture_output=False)
    def contextualize_sync(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """Synchronous contextualization using OpenAI.

        SDK-native retries via ``max_retries`` on the sync OpenAI client.
        """
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
