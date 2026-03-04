"""Tests for contextualize_batch() parallel chunk processing."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.contextualization.base import ContextualizedChunk, ContextualizeProvider
from src.contextualization.claude import ClaudeContextualizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SimpleContextualizer(ContextualizeProvider):
    """Minimal concrete implementation for testing the base-class method."""

    async def contextualize(
        self,
        chunks: list[str],
        query: str | None = None,
        context_window: int = 3,
    ) -> list[ContextualizedChunk]:
        return []

    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: str | None = None,
    ) -> ContextualizedChunk:
        return ContextualizedChunk(
            original_text=text,
            contextual_summary=f"Summary of {article_number}",
            article_number=article_number,
            context_method="test",
        )


# ---------------------------------------------------------------------------
# Base-class tests
# ---------------------------------------------------------------------------


class TestContextualizeBatch:
    """contextualize_batch() behaviour via base class."""

    @pytest.mark.asyncio
    async def test_all_chunks_processed(self) -> None:
        ctx = _SimpleContextualizer()
        results = await ctx.contextualize_batch(["a", "b", "c"])
        assert len(results) == 3
        assert all(isinstance(r, ContextualizedChunk) for r in results)

    @pytest.mark.asyncio
    async def test_order_preserved(self) -> None:
        ctx = _SimpleContextualizer()
        chunks = ["first", "second", "third"]
        results = await ctx.contextualize_batch(chunks)
        assert [r.original_text for r in results] == chunks

    @pytest.mark.asyncio
    async def test_empty_input(self) -> None:
        ctx = _SimpleContextualizer()
        assert await ctx.contextualize_batch([]) == []

    @pytest.mark.asyncio
    async def test_article_numbers_generated(self) -> None:
        ctx = _SimpleContextualizer()
        results = await ctx.contextualize_batch(["x", "y"])
        assert results[0].article_number == "chunk_0"
        assert results[1].article_number == "chunk_1"

    @pytest.mark.asyncio
    async def test_query_forwarded(self) -> None:
        received: list[str | None] = []

        class _Tracker(_SimpleContextualizer):
            async def contextualize_single(self, text, article_number, query=None):
                received.append(query)
                return await super().contextualize_single(text, article_number, query)

        await _Tracker().contextualize_batch(["a", "b"], query="find X")
        assert received == ["find X", "find X"]

    @pytest.mark.asyncio
    async def test_failures_return_fallback_chunks(self) -> None:
        class _FailsOnSecond(_SimpleContextualizer):
            async def contextualize_single(self, text, article_number, query=None):
                if article_number == "chunk_1":
                    raise RuntimeError("boom")
                return await super().contextualize_single(text, article_number, query)

        results = await _FailsOnSecond().contextualize_batch(["a", "b", "c"])

        assert len(results) == 3
        assert results[0].context_method == "test"
        assert results[1].original_text == "b"
        assert results[1].context_method == "none"
        assert results[1].article_number == "chunk_1"
        assert results[2].context_method == "test"

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        active = 0
        peak = 0

        class _TrackingContextualizer(ContextualizeProvider):
            async def contextualize(self, chunks, query=None, context_window=3):
                return []

            async def contextualize_single(self, text, article_number, query=None):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1
                return ContextualizedChunk(
                    original_text=text,
                    contextual_summary="s",
                    article_number=article_number,
                    context_method="test",
                )

        chunks = [f"chunk_{i}" for i in range(10)]
        await _TrackingContextualizer().contextualize_batch(chunks, max_concurrency=3)
        assert peak <= 3

    @pytest.mark.asyncio
    async def test_default_max_concurrency_is_five(self) -> None:
        """Smoke-check: 5 chunks with default concurrency = 5 all complete."""
        ctx = _SimpleContextualizer()
        results = await ctx.contextualize_batch([f"c{i}" for i in range(5)])
        assert len(results) == 5


# ---------------------------------------------------------------------------
# ClaudeContextualizer tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = "test-key"
    s.model_name = "claude-3-haiku-20240307"
    return s


@pytest.fixture()
def claude_ctx(mock_settings: MagicMock) -> ClaudeContextualizer:
    with (
        patch("src.contextualization.claude.AsyncAnthropic"),
        patch("src.contextualization.claude.Anthropic"),
    ):
        return ClaudeContextualizer(settings=mock_settings)


class TestClaudeContextualizerBatch:
    """contextualize_batch() on ClaudeContextualizer."""

    @pytest.mark.asyncio
    async def test_all_chunks_processed(self, claude_ctx: ClaudeContextualizer) -> None:
        call_count = 0

        async def _mock_single(text: str, article_number: str, query=None) -> ContextualizedChunk:
            nonlocal call_count
            call_count += 1
            return ContextualizedChunk(
                original_text=text,
                contextual_summary="ctx",
                article_number=article_number,
                context_method="claude",
            )

        claude_ctx.contextualize_single = _mock_single  # type: ignore[method-assign]
        results = await claude_ctx.contextualize_batch(["a", "b", "c", "d", "e"])
        assert len(results) == 5
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_order_preserved_with_variable_latency(
        self, claude_ctx: ClaudeContextualizer
    ) -> None:
        async def _mock_single(text: str, article_number: str, query=None) -> ContextualizedChunk:
            # Slowest chunk first — order must still be maintained
            delay = 0.02 if article_number == "chunk_0" else 0.001
            await asyncio.sleep(delay)
            return ContextualizedChunk(
                original_text=text,
                contextual_summary="ctx",
                article_number=article_number,
                context_method="claude",
            )

        claude_ctx.contextualize_single = _mock_single  # type: ignore[method-assign]
        chunks = ["slow", "fast1", "fast2"]
        results = await claude_ctx.contextualize_batch(chunks)
        assert [r.original_text for r in results] == chunks

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, claude_ctx: ClaudeContextualizer) -> None:
        active = 0
        peak = 0

        async def _mock_single(text: str, article_number: str, query=None) -> ContextualizedChunk:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return ContextualizedChunk(
                original_text=text,
                contextual_summary="ctx",
                article_number=article_number,
                context_method="claude",
            )

        claude_ctx.contextualize_single = _mock_single  # type: ignore[method-assign]
        await claude_ctx.contextualize_batch([f"c{i}" for i in range(10)], max_concurrency=2)
        assert peak <= 2
