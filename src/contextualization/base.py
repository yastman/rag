"""Base class for contextualization providers."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langfuse import observe


@dataclass
class ContextualizedChunk:
    """Chunk with added context and metadata."""

    original_text: str
    contextual_summary: str  # LLM-generated context
    article_number: str
    chapter: str | None = None
    section: str | None = None
    context_method: str = "none"  # 'claude', 'openai', 'groq'
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def full_text(self) -> str:
        """Combined original + contextual text."""
        return f"{self.contextual_summary}\n\n{self.original_text}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "original_text": self.original_text,
            "contextual_summary": self.contextual_summary,
            "article_number": self.article_number,
            "chapter": self.chapter,
            "section": self.section,
            "context_method": self.context_method,
            "timestamp": self.timestamp.isoformat(),
            "full_text": self.full_text,
        }


class ContextualizeProvider(ABC):
    """
    Abstract base class for document contextualization.

    Contextualization enriches documents with LLM-generated summaries,
    improving retrieval quality by providing semantic context.

    Performance Impact:
    - +2-5% improvement in Recall@1
    - +0.5-1% improvement in NDCG@10
    - Cost: Varies by provider (Claude: ~$0.01/chunk)
    """

    @abstractmethod
    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize a list of text chunks."""
        _ = context_window
        raise NotImplementedError

    @abstractmethod
    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """Contextualize a single chunk."""

    async def contextualize_batch(
        self,
        chunks: list[str],
        query: str | None = None,
        *,
        max_concurrency: int = 5,
    ) -> list[ContextualizedChunk]:
        """Contextualize chunks in parallel using asyncio.gather with semaphore."""
        sem = asyncio.Semaphore(max_concurrency)

        async def _process_with_semaphore(index: int, chunk: str) -> ContextualizedChunk:
            async with sem:
                return await self.contextualize_single(chunk, f"chunk_{index}", query)

        results = await asyncio.gather(
            *[_process_with_semaphore(i, chunk) for i, chunk in enumerate(chunks)],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, ContextualizedChunk)]

    @staticmethod
    def get_system_prompt() -> str:
        """Get the system prompt for contextualization."""
        return """You are an expert legal document analyzer for Ukrainian law.
Your task is to generate brief, focused contextual summaries of legal text snippets.

Guidelines:
1. Create a 1-2 sentence summary that captures the essential legal meaning
2. Highlight key concepts, obligations, or rights mentioned
3. Maintain legal accuracy and formality
4. Keep summaries concise (max 100 words)
5. Focus on what makes this clause important in its legal context

Respond ONLY with the summary, no additional explanation."""

    @staticmethod
    def get_user_prompt(text: str, query: str | None = None) -> str:
        """Get the user prompt for contextualization."""
        base = f"Summarize this legal text in context:\n\n{text}"
        if query:
            base += f"\n\nUser is searching for: {query}"
        return base


class BaseContextualizationProvider(ContextualizeProvider):
    """
    Shared base for LLM-backed contextualization providers.

    Extracts the common batch loop with fallback pattern shared across
    Claude, OpenAI, and Groq providers (~80% code duplication eliminated).

    Subclasses only need to implement:
    - ``_call_llm_async``: single async LLM call returning (text, prompt_tokens, completion_tokens)
    - ``_call_llm_sync``: single sync LLM call returning (text, prompt_tokens, completion_tokens)
    - ``context_method``: provider identifier string ('claude', 'openai', 'groq')
    - ``get_stats``: provider-specific statistics dict (optional override)

    Token/cost tracking:
    - ``total_tokens`` accumulated automatically from _call_llm_* return values
    - ``total_cost`` accumulated via ``cost_per_input_token`` / ``cost_per_output_token``
    """

    context_method: str = "none"

    # Override in subclasses to enable cost tracking (cost in USD per token)
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0

    def __init__(self) -> None:
        self.total_tokens: int = 0
        self.total_cost: float = 0.0

    @abstractmethod
    async def _call_llm_async(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute single async LLM call.

        Returns:
            Tuple of (generated_text, prompt_tokens, completion_tokens)
        """

    @abstractmethod
    def _call_llm_sync(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int, int]:
        """Execute single sync LLM call.

        Returns:
            Tuple of (generated_text, prompt_tokens, completion_tokens)
        """

    def _track_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Accumulate token and cost counters."""
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost += (
            prompt_tokens * self.cost_per_input_token
            + completion_tokens * self.cost_per_output_token
        )

    @observe(name="contextualize-batch", capture_input=False, capture_output=False)
    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        """Contextualize multiple chunks sequentially with per-chunk fallback."""
        _ = context_window
        results: list[ContextualizedChunk] = []
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
        """Contextualize a single chunk (async)."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)
        summary, prompt_tokens, completion_tokens = await self._call_llm_async(
            system_prompt, user_prompt
        )
        self._track_usage(prompt_tokens, completion_tokens)
        if not summary.strip():
            raise ValueError(f"Empty response from {self.context_method}")
        return ContextualizedChunk(
            original_text=text,
            contextual_summary=summary,
            article_number=article_number,
            context_method=self.context_method,
        )

    def contextualize_sync(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """Contextualize a single chunk (sync/blocking)."""
        system_prompt = self.get_system_prompt()
        user_prompt = self.get_user_prompt(text, query)
        summary, prompt_tokens, completion_tokens = self._call_llm_sync(
            system_prompt, user_prompt
        )
        self._track_usage(prompt_tokens, completion_tokens)
        return ContextualizedChunk(
            original_text=text,
            contextual_summary=summary,
            article_number=article_number,
            context_method=self.context_method,
        )

    def get_stats(self) -> dict[str, int | float]:
        """Return token/cost statistics. Override for provider-specific fields."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }
