"""Tests for async anti-patterns fixed in #862.

Verifies that:
- VoyageEmbedFunction.__call__ uses asyncio.run() (not get_event_loop().run_until_complete())
- StateManager._run_sync uses asyncio.run() (not new_event_loop() + run_until_complete())
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np


class TestVoyageEmbedFunctionUsesAsyncioRun:
    """VoyageEmbedFunction.__call__ should use asyncio.run, not event loop manipulation."""

    def test_call_uses_asyncio_run_not_get_event_loop(self) -> None:
        """__call__ must use asyncio.run() instead of get_event_loop().run_until_complete()."""
        from src.ingestion.cocoindex_flow import VoyageEmbedFunction

        func = VoyageEmbedFunction(api_key="test-key")
        mock_service = MagicMock()
        mock_service.embed_documents = AsyncMock(return_value=[[0.1, 0.2]])
        func._service = mock_service

        with (
            patch("asyncio.run", return_value=[[0.1, 0.2]]) as mock_asyncio_run,
            patch("asyncio.get_event_loop") as mock_get_loop,
        ):
            func(["text1"])

        # asyncio.run must be used
        mock_asyncio_run.assert_called_once()
        # get_event_loop must NOT be called (anti-pattern removed)
        mock_get_loop.assert_not_called()

    def test_call_does_not_use_concurrent_futures(self) -> None:
        """__call__ must not spawn ThreadPoolExecutor to bridge sync/async."""
        from src.ingestion.cocoindex_flow import VoyageEmbedFunction

        func = VoyageEmbedFunction(api_key="test-key")
        mock_service = MagicMock()
        mock_service.embed_documents = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        func._service = mock_service

        with (
            patch("asyncio.run", return_value=[[0.1, 0.2, 0.3]]),
            patch("concurrent.futures.ThreadPoolExecutor") as mock_executor,
        ):
            func(["text1"])

        mock_executor.assert_not_called()

    def test_call_returns_numpy_arrays(self) -> None:
        """__call__ must still return list[NDArray[float32]] after refactor."""
        from src.ingestion.cocoindex_flow import VoyageEmbedFunction

        func = VoyageEmbedFunction(api_key="test-key")
        mock_service = MagicMock()
        mock_service.embed_documents = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        func._service = mock_service

        with patch("asyncio.run", return_value=[[0.1, 0.2, 0.3]]):
            result = func(["text1"])

        assert len(result) == 1
        assert isinstance(result[0], np.ndarray)
        assert result[0].dtype == np.float32


class TestStateManagerRunSyncUsesAsyncioRun:
    """StateManager._run_sync should use asyncio.run(), not new_event_loop()."""

    def test_run_sync_standalone_uses_asyncio_run(self) -> None:
        """_run_sync standalone path must call asyncio.run(), not new_event_loop()."""
        from src.ingestion.unified.state_manager import UnifiedStateManager

        # Create instance without __init__ to avoid DB connections
        sm = UnifiedStateManager.__new__(UnifiedStateManager)
        sm._runner = None  # not inside sync_context
        sm._pool = None

        async def dummy_coro() -> str:
            return "result"

        with (
            patch("asyncio.run", return_value="result") as mock_run,
            patch("asyncio.new_event_loop") as mock_new_loop,
        ):
            out = sm._run_sync(dummy_coro())

        mock_run.assert_called_once()
        mock_new_loop.assert_not_called()
        assert out == "result"

    def test_run_sync_standalone_does_not_call_run_until_complete(self) -> None:
        """_run_sync must not call loop.run_until_complete() on standalone calls."""
        from src.ingestion.unified.state_manager import UnifiedStateManager

        sm = UnifiedStateManager.__new__(UnifiedStateManager)
        sm._runner = None
        sm._pool = None

        mock_loop = MagicMock()

        async def dummy_coro() -> int:
            return 42

        with (
            patch("asyncio.run", return_value=42),
            patch("asyncio.new_event_loop", return_value=mock_loop),
        ):
            out = sm._run_sync(dummy_coro())

        # run_until_complete on a manually-created loop must not be called
        mock_loop.run_until_complete.assert_not_called()
        assert out == 42
