"""Contract test: issue #2325 Qdrant preflight fallback semantics.

1) Primary `AsyncQdrantClient(..., prefer_grpc=True)` failure should not falsely fail
   startup when REST transport can validate the same collection checks.
2) Empty exception messages must still produce non-empty diagnostics and must be
   rendered into the startup report, especially for CRITICAL qdrant failures.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.preflight import _build_dependency_report, _check_single_dep


@pytest.mark.asyncio
async def test_qdrant_grpc_exception_can_fallback_to_rest_transport(caplog):
    """Preflight should pass when primary gRPC fails and REST SDK check passes."""
    config = MagicMock()
    config.qdrant_url = "http://localhost:6333"
    config.qdrant_api_key = None
    config.qdrant_timeout = 30
    config.get_collection_name = MagicMock(return_value="test_col")
    config.qdrant_collection = "test_col"

    info = MagicMock()
    info.points_count = 7
    info.config.params.vectors = {"dense": MagicMock(), "colbert": MagicMock()}
    info.config.params.sparse_vectors = {"bm42": MagicMock()}

    fallback_client = AsyncMock()
    fallback_client.info = AsyncMock()
    fallback_client.collection_exists = AsyncMock(return_value=True)
    fallback_client.get_collection = AsyncMock(return_value=info)
    fallback_client.close = AsyncMock()

    with (
        patch(
            "telegram_bot.preflight.AsyncQdrantClient",
            side_effect=[Exception(), fallback_client],
        ) as create_client,
        caplog.at_level(logging.WARNING),
    ):
        client = AsyncMock(spec=httpx.AsyncClient)
        result = await _check_single_dep("qdrant", config, client)

    assert result is True
    assert len(create_client.call_args_list) == 2

    first_call_kwargs = create_client.call_args_list[0].kwargs
    second_call_kwargs = create_client.call_args_list[1].kwargs
    assert first_call_kwargs["prefer_grpc"] is True
    assert second_call_kwargs.get("prefer_grpc") is False

    assert any("primary gRPC preflight failed" in rec.message for rec in caplog.records)

    # Empty exception messages must still be rendered as non-empty diagnostic text.
    assert any("empty exception message" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_qdrant_grpc_collection_exists_exception_can_fallback_to_rest_transport():
    """Primary SDK call exceptions should trigger REST fallback, not hard-fail."""
    config = MagicMock()
    config.qdrant_url = "http://localhost:6333"
    config.qdrant_api_key = None
    config.qdrant_timeout = 30
    config.get_collection_name = MagicMock(return_value="test_col")
    config.qdrant_collection = "test_col"

    info = MagicMock()
    info.points_count = 0
    info.config.params.vectors = {"dense": MagicMock()}
    info.config.params.sparse_vectors = {"bm42": MagicMock()}

    primary_client = AsyncMock()
    primary_client.info = AsyncMock()
    primary_client.collection_exists = AsyncMock(side_effect=RuntimeError("grpc unavailable"))
    primary_client.close = AsyncMock()

    fallback_client = AsyncMock()
    fallback_client.info = AsyncMock()
    fallback_client.collection_exists = AsyncMock(return_value=True)
    fallback_client.get_collection = AsyncMock(return_value=info)
    fallback_client.close = AsyncMock()

    with patch(
        "telegram_bot.preflight.AsyncQdrantClient",
        side_effect=[primary_client, fallback_client],
    ) as create_client:
        client = AsyncMock(spec=httpx.AsyncClient)
        result = await _check_single_dep("qdrant", config, client)

    assert result is True
    assert len(create_client.call_args_list) == 2
    assert create_client.call_args_list[0].kwargs["prefer_grpc"] is True
    assert create_client.call_args_list[1].kwargs["prefer_grpc"] is False
    fallback_client.get_collection.assert_awaited_once_with("test_col")


@pytest.mark.asyncio
async def test_qdrant_empty_exceptions_are_reported_in_dependency_summary():
    """Both primary and REST exceptions must produce a non-empty qdrant reason."""
    config = MagicMock()
    config.qdrant_url = "http://localhost:6333"
    config.qdrant_api_key = None
    config.qdrant_timeout = 30
    config.get_collection_name = MagicMock(return_value="test_col")
    config.qdrant_collection = "test_col"

    reasons: dict[str, str] = {}

    with (
        patch("telegram_bot.preflight.AsyncQdrantClient", side_effect=[Exception(), Exception()]),
    ):
        client = AsyncMock(spec=httpx.AsyncClient)
        result = await _check_single_dep("qdrant", config, client, failure_reasons=reasons)

    assert result is False
    assert reasons.get("qdrant")
    assert "empty exception message" in reasons["qdrant"].lower()

    report = _build_dependency_report({"qdrant": False}, failures=reasons)
    rendered = report.render()
    assert "qdrant" in rendered
    assert "empty exception message" in rendered
