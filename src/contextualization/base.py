"""Base class for contextualization providers."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


# Anthropic prompt-caching pricing multipliers (relative to base input price).
# Source: Anthropic pricing docs — cache creation is billed at 1.25× input
# price, cache reads at 0.10× input price.
_CACHE_CREATION_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10

_DEFAULT_SYSTEM_PROMPT = """You are an expert legal document analyzer for Ukrainian law.
Your task is to generate brief, focused contextual summaries of legal text snippets.

Guidelines:
1. Create a 1-2 sentence summary that captures the essential legal meaning
2. Highlight key concepts, obligations, or rights mentioned
3. Maintain legal accuracy and formality
4. Keep summaries concise (max 100 words)
5. Focus on what makes this clause important in its legal context

Respond ONLY with the summary, no additional explanation."""


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

    def __init__(self, *, system_prompt: str | None = None) -> None:
        """Initialize shared provider state."""
        self.system_prompt = self.get_system_prompt(system_prompt)

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
        """Contextualize chunks in parallel using asyncio.TaskGroup.

        Per-chunk failures are caught inside each worker so the TaskGroup
        stays alive and produces a fallback ``ContextualizedChunk`` with
        ``context_method="none"`` and an empty ``contextual_summary`` at
        the failed index. Output cardinality and order match the input
        list (#1656). Callers can filter on ``context_method`` to detect
        which chunks were skipped.

        Args:
            chunks: List of text chunks to contextualize
            query: Optional user query to guide contextualization
            max_concurrency: Maximum simultaneous API calls (default: 5)

        Returns:
            List of contextualized chunks preserving input order. Failed
            chunks are represented as fallback records, never dropped.
        """
        sem = asyncio.Semaphore(max_concurrency)
        # Pre-allocate so each task can write to its index slot — preserves
        # order without sorting after the fact.
        results: list[ContextualizedChunk] = [
            ContextualizedChunk(
                original_text="",
                contextual_summary="",
                article_number="",
                context_method="none",
            )
            for _ in chunks
        ]

        async def _process(index: int, chunk: str) -> None:
            async with sem:
                try:
                    results[index] = await self.contextualize_single(chunk, f"chunk_{index}", query)
                except Exception as exc:
                    logger.warning("contextualize_batch chunk %d failed: %s", index, exc)
                    results[index] = ContextualizedChunk(
                        original_text=chunk,
                        contextual_summary="",
                        article_number=f"chunk_{index}",
                        context_method="none",
                    )

        if not chunks:
            return []
        async with asyncio.TaskGroup() as tg:
            for i, chunk in enumerate(chunks):
                tg.create_task(_process(i, chunk))

        return results

    @staticmethod
    def get_system_prompt(prompt: str | None = None) -> str:
        """Return the system prompt for contextualization (issue #1234).

        Callers can pass a custom prompt to reuse the contextualizers in
        non-legal domains. When no prompt is given (or the override is
        empty/whitespace), the default Ukrainian-legal prompt is returned
        so existing callers keep working unchanged.
        """
        if prompt is not None and prompt.strip():
            return prompt
        return _DEFAULT_SYSTEM_PROMPT

    @staticmethod
    def get_user_prompt(text: str, query: str | None = None) -> str:
        """Get the user prompt for contextualization."""
        base = f"Summarize this legal text in context:\n\n{text}"
        if query:
            base += f"\n\nUser is searching for: {query}"
        return base

    # ------------------------------------------------------------------
    # Cost tracking helpers (issue #1234) — shared across providers.
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_token_cost(
        *,
        input_tokens: int,
        output_tokens: int,
        input_price_per_mtok: float,
        output_price_per_mtok: float,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Compute USD cost for a single API call.

        ``input_price_per_mtok`` and ``output_price_per_mtok`` are USD per 1M
        tokens — the convention every major SDK pricing page uses.

        Anthropic prompt caching is supported via the optional
        ``cache_creation_tokens`` and ``cache_read_tokens`` arguments. Cache
        creation tokens are billed at 1.25× the base input price, cache reads
        at 0.10× — both relative to ``input_price_per_mtok``. Providers without
        prompt caching (OpenAI, Groq) simply omit these arguments.
        """
        cost = (
            input_tokens * input_price_per_mtok
            + output_tokens * output_price_per_mtok
            + cache_creation_tokens * input_price_per_mtok * _CACHE_CREATION_MULTIPLIER
            + cache_read_tokens * input_price_per_mtok * _CACHE_READ_MULTIPLIER
        )
        return cost / 1_000_000

    @staticmethod
    def _coerce_token_count(value: Any) -> int:
        """Return ``value`` as a non-negative int, treating non-numeric input as 0.

        Used to defend against ``MagicMock`` auto-attributes (whose ``__int__``
        defaults to 1) leaking into token accounting from test fixtures.
        """
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return 0

    @staticmethod
    def _total_input_tokens_from_anthropic_usage(usage: Any) -> int:
        """Sum the three input-token fields the Anthropic SDK exposes.

        Per the Anthropic SDK docstring (``anthropic.types.message.Usage``)::

            Total input tokens in a request is the summation of input_tokens,
            cache_creation_input_tokens, and cache_read_input_tokens.

        Cache fields are optional on the Usage object and may be absent or
        ``None`` when prompt caching is not used; the helper treats both
        cases as zero so non-cached requests still report correctly.
        """

        def _coerce(value: Any) -> int:
            # Strict numeric check so a MagicMock auto-attribute (which
            # answers ``__int__`` with ``1``) is not mistaken for a real
            # token count from the SDK.
            if isinstance(value, bool):
                return 0
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            return 0

        return (
            _coerce(getattr(usage, "input_tokens", 0))
            + _coerce(getattr(usage, "cache_creation_input_tokens", 0))
            + _coerce(getattr(usage, "cache_read_input_tokens", 0))
        )
