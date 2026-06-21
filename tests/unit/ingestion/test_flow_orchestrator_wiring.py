"""Regression tests for run_once/run_watch orchestrator wiring (#2940).

Asserts that run_once and run_watch delegate to UnifiedIngestionOrchestrator
and never silently no-op (the bug fixed in #2940).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def test_run_once_calls_orchestrator_run_once(tmp_path: Path) -> None:
    """run_once must call orchestrator.run_once, not silently return."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import run_once

    config = UnifiedConfig(sync_dir=tmp_path)
    mock_orch = MagicMock()
    mock_orch.run_once = AsyncMock(return_value=MagicMock(processed=1, deleted=0, errors=0))

    with patch("src.ingestion.unified.flow._build_orchestrator", return_value=mock_orch):
        run_once(config)

    mock_orch.run_once.assert_called_once_with(config.collection_name)


def test_run_once_does_not_raise_notimplemented(tmp_path: Path) -> None:
    """run_once must not raise NotImplementedError (the no-op bug from #2940)."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import run_once

    config = UnifiedConfig(sync_dir=tmp_path)
    mock_orch = MagicMock()
    mock_orch.run_once = AsyncMock(return_value=MagicMock(processed=0, deleted=0, errors=0))

    with patch("src.ingestion.unified.flow._build_orchestrator", return_value=mock_orch):
        # Must not raise NotImplementedError
        run_once(config)


def test_run_watch_calls_orchestrator_run_watch(tmp_path: Path) -> None:
    """run_watch must call orchestrator.run_watch, not silently return."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import run_watch

    config = UnifiedConfig(sync_dir=tmp_path)
    stop = asyncio.Event()
    stop.set()  # pre-set so run_watch exits immediately

    mock_orch = MagicMock()
    mock_orch.run_watch = AsyncMock(return_value=None)

    with patch("src.ingestion.unified.flow._build_orchestrator", return_value=mock_orch):
        run_watch(config, stop_event=stop)

    mock_orch.run_watch.assert_called_once()


def test_run_once_flag_not_required(tmp_path: Path) -> None:
    """INGEST_USE_NEW_ORCHESTRATOR flag is no longer required; run_once works without it."""
    import os

    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import run_once

    config = UnifiedConfig(sync_dir=tmp_path)
    mock_orch = MagicMock()
    mock_orch.run_once = AsyncMock(return_value=MagicMock(processed=0, deleted=0, errors=0))

    env_without_flag = {k: v for k, v in os.environ.items() if k != "INGEST_USE_NEW_ORCHESTRATOR"}
    with (
        patch.dict(os.environ, env_without_flag, clear=True),
        patch("src.ingestion.unified.flow._build_orchestrator", return_value=mock_orch),
    ):
        run_once(config)  # must not raise

    mock_orch.run_once.assert_called_once()
