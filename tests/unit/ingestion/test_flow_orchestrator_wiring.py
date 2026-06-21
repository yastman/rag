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


async def test_write_file_returns_persisted_state_not_stripped(tmp_path: Path, monkeypatch) -> None:
    """write_file must return the persisted FileState (content_hash set).

    Regression for #2940: mutate() persists the authoritative state
    (content_hash, embedding_model, pipeline_version), but write_file used to
    return a stripped FileState(content_hash=None). record_state then
    flat-overwrote the good row with NULLs, so every poll re-classified the
    file as 'added' and re-ingested everything. write_file must read the
    persisted state back instead.
    """
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import _build_orchestrator
    from src.ingestion.unified.state_manager import FileState

    doc = tmp_path / "doc.md"
    doc.write_text("hello world")

    persisted = FileState(
        file_id="fid-persisted",
        source_path=str(doc),
        content_hash="deadbeefcafebabe",
        embedding_model="bge-m3-api",
        pipeline_version="v3.2.1",
        status="indexed",
    )

    class _FakeStateManager:
        """Stands in for the Postgres row mutate() would have written."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def get_state(self, file_id: str) -> FileState:
            return persisted

    # mutate() is the real (sync, network) persistence path; stub it so the
    # test stays unit-level. The FakeStateManager represents the row it wrote.
    monkeypatch.setattr(
        "src.ingestion.unified.targets.qdrant_hybrid_target.QdrantHybridTargetConnector.mutate",
        classmethod(lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        "src.ingestion.unified.state_manager.UnifiedStateManager",
        _FakeStateManager,
    )

    orch = _build_orchestrator(UnifiedConfig(sync_dir=tmp_path))
    result = await orch.writer.write_file(str(doc), "test_collection")

    assert result.content_hash == "deadbeefcafebabe"
    assert result.embedding_model == "bge-m3-api"
    assert result.pipeline_version == "v3.2.1"


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
