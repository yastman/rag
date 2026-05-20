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


# ---------------------------------------------------------------------------
# Failure surfacing (#1656) — TaskGroup contract
# ---------------------------------------------------------------------------


class TestContextualizeBatchFailureSurfacing:
    """contextualize_batch must NOT silently drop failed chunks (#1656).

    Previous behavior used asyncio.gather(..., return_exceptions=True) and
    filtered exceptions out, dropping the chunks entirely. New contract:
    failures surface as fallback ContextualizedChunk records with
    context_method='none' at the correct index, preserving cardinality
    and order.

    SDK baseline: asyncio.TaskGroup (PEP 654, Python 3.11+) is the
    structured-concurrency primitive. Per-task try/except inside the
    TaskGroup body keeps the group alive while recording per-chunk
    failure outcomes.
    """

    @pytest.mark.asyncio
    async def test_failed_chunks_produce_fallback_record_at_correct_index(self) -> None:
        class _FlakyContextualizer(ContextualizeProvider):
            async def contextualize(self, chunks, query=None, context_window=3):
                return []

            async def contextualize_single(self, text, article_number, query=None):
                if "fail" in text:
                    raise RuntimeError(f"boom: {text}")
                return ContextualizedChunk(
                    original_text=text,
                    contextual_summary=f"ok: {text}",
                    article_number=article_number,
                    context_method="test",
                )

        chunks = ["ok-0", "fail-1", "ok-2", "fail-3", "ok-4"]
        results = await _FlakyContextualizer().contextualize_batch(chunks)

        # No silent drops: cardinality preserved.
        assert len(results) == len(chunks)
        # Order preserved by index.
        assert [r.original_text for r in results] == chunks
        # Failed slots carry context_method='none'; succeeded slots keep 'test'.
        methods = [r.context_method for r in results]
        assert methods == ["test", "none", "test", "none", "test"]
        # Failed slots have empty summary so downstream filtering is clear.
        assert results[1].contextual_summary == ""
        assert results[3].contextual_summary == ""

    @pytest.mark.asyncio
    async def test_all_failed_returns_fallbacks_not_empty_list(self) -> None:
        class _AlwaysFails(ContextualizeProvider):
            async def contextualize(self, chunks, query=None, context_window=3):
                return []

            async def contextualize_single(self, text, article_number, query=None):
                raise RuntimeError("always")

        results = await _AlwaysFails().contextualize_batch(["a", "b"])
        assert len(results) == 2
        assert all(r.context_method == "none" for r in results)
        # Article numbers still indexed for traceability.
        assert results[0].article_number == "chunk_0"
        assert results[1].article_number == "chunk_1"

    def test_base_module_uses_task_group_not_silent_gather(self) -> None:
        """AST contract: contextualize_batch uses TaskGroup; no return_exceptions=True."""
        import ast
        import inspect
        import textwrap

        from src.contextualization import base as mod

        source = textwrap.dedent(inspect.getsource(mod.ContextualizeProvider.contextualize_batch))
        tree = ast.parse(source)

        uses_task_group = False
        uses_silent_gather = False

        for node in ast.walk(tree):
            # asyncio.TaskGroup() — accept attribute or name reference.
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "TaskGroup":
                    uses_task_group = True
                if isinstance(func, ast.Name) and func.id == "TaskGroup":
                    uses_task_group = True
                # asyncio.gather(..., return_exceptions=True) — forbidden silent drop.
                if (isinstance(func, ast.Attribute) and func.attr == "gather") or (
                    isinstance(func, ast.Name) and func.id == "gather"
                ):
                    for kw in node.keywords:
                        if (
                            kw.arg == "return_exceptions"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            uses_silent_gather = True

        assert uses_task_group, (
            "contextualize_batch must use asyncio.TaskGroup for structured concurrency (#1656)"
        )
        assert not uses_silent_gather, (
            "contextualize_batch must not call asyncio.gather(..., "
            "return_exceptions=True) — failures must be surfaced explicitly"
        )
