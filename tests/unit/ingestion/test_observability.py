"""Tests for unified ingestion observability helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.ingestion.unified.observability import update_ingestion_trace


def test_update_ingestion_trace_uses_observation_updates() -> None:
    mock_lf = MagicMock()
    mock_observation = MagicMock()
    mock_observation_ctx = MagicMock()
    mock_observation_ctx.__enter__ = MagicMock(return_value=mock_observation)
    mock_observation_ctx.__exit__ = MagicMock(return_value=None)
    mock_lf.start_as_current_observation.return_value = mock_observation_ctx
    mock_lf.create_trace_id.return_value = "trace-ingestion-preflight"
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=None)
    mock_context.__exit__ = MagicMock(return_value=None)

    with (
        patch("src.ingestion.unified.observability.get_client", return_value=mock_lf),
        patch(
            "src.ingestion.unified.observability.propagate_attributes",
            return_value=mock_context,
        ) as mock_propagate,
    ):
        update_ingestion_trace(command="preflight", status="ok", metadata={"step": "boot"})

    mock_lf.create_trace_id.assert_called_once_with(seed="ingestion-preflight")
    mock_lf.start_as_current_observation.assert_called_once_with(
        as_type="span",
        name="ingestion-preflight",
        trace_context={"trace_id": "trace-ingestion-preflight"},
    )
    mock_propagate.assert_called_once_with(
        session_id="ingestion-preflight",
        user_id="ingestion-cli",
        tags=["ingestion", "unified"],
    )
    mock_observation.update.assert_called_once_with(
        metadata={"command": "preflight", "status": "ok", "step": "boot"}
    )
