"""Base class for contextualization providers."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
        """
        Contextualize a list of text chunks.

        Args:
            chunks: List of text chunks to contextualize
            query: Optional user query to guide contextualization
            context_window: Number of surrounding chunks to consider

        Returns:
            List of contextualized chunks with metadata
        """
        _ = context_window
        raise NotImplementedError

    @abstractmethod
    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        """
        Contextualize a single chunk.

        Args:
            text: Text to contextualize
            article_number: Article/section identifier
            query: Optional user query

        Returns:
            Contextualized chunk with metadata
        """

    async def contextualize_batch(
        self,
        chunks: list[str],
        query: str | None = None,
        *,
        max_concurrency: int = 5,
    ) -> list[ContextualizedChunk]:
        """Contextualize chunks in parallel using asyncio.gather with semaphore.

        Args:
            chunks: List of text chunks to contextualize
            query: Optional user query to guide contextualization
            max_concurrency: Maximum simultaneous API calls (default: 5)

        Returns:
            List of contextualized chunks preserving input order
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _process_with_semaphore(index: int, chunk: str) -> ContextualizedChunk:
            async with sem:
                return await self.contextualize_single(chunk, f"chunk_{index}", query)

        return list(
            await asyncio.gather(
                *[_process_with_semaphore(i, chunk) for i, chunk in enumerate(chunks)]
            )
        )

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
