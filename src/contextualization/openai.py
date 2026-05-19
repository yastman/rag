"""OpenAI-based contextualization provider."""

from langfuse import observe
from langfuse.openai import AsyncOpenAI, OpenAI
from openai import APIStatusError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from src.config import Settings

from .base import BaseContextualizationProvider, ContextualizedChunk


class OpenAIContextualizer(BaseContextualizationProvider):
    """
    Contextualize documents using OpenAI GPT API.

    Performance:
    - ~5-8 minutes for 100 chunks
    - Cost: ~$0.008-0.012 per chunk
    - Quality: Very good
    """

    context_method = "openai"

    # OpenAI pricing: $5/MTok input, $15/MTok output (gpt-4o-mini)
    cost_per_input_token: float = 5 / 1_000_000
    cost_per_output_token: float = 15 / 1_000_000

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize OpenAI contextualizer."""
        super().__init__()
        self.settings = settings or Settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.sync_client = OpenAI(api_key=self.settings.openai_api_key)

    @observe(name="openai-contextualize-batch", capture_input=False, capture_output=False)
    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks using OpenAI."""
        return await super().contextualize(chunks, query, context_window)

    @observe(name="openai-contextualize", capture_input=False, capture_output=False)
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
        """Contextualize a single chunk using OpenAI (with retry)."""
        return await super().contextualize_single(text, article_number, query)

    async def _call_llm_async(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute OpenAI API call."""
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
        usage = response.usage
        prompt_tokens = int(usage.prompt_tokens or 0) if usage else 0
        completion_tokens = int(usage.completion_tokens or 0) if usage else 0
        return response.choices[0].message.content or "", prompt_tokens, completion_tokens

    @observe(name="openai-contextualize-sync", capture_input=False, capture_output=False)
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
        return super().contextualize_sync(text, article_number, query)

    def _call_llm_sync(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute sync OpenAI API call."""
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
        prompt_tokens = int(usage.prompt_tokens or 0) if usage else 0
        completion_tokens = int(usage.completion_tokens or 0) if usage else 0
        return response.choices[0].message.content or "", prompt_tokens, completion_tokens
