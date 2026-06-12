"""Tests for core telemetry event dispatch."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest


class _FakeCache:
    async def check_semantic(self, *args: object, **kwargs: object) -> dict[str, Any] | None:
        return None


class _FakeEmbeddings:
    async def aembed_query(self, text: str) -> list[float]:
        return [0.0]


class _FakeSparseEmbeddings:
    async def aembed_query(self, text: str) -> dict[str, Any]:
        return {}


class _FakeQdrant:
    async def hybrid_search_rrf(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
        return []


class _FailingTelemetry:
    def log_event(self, event: str, **fields: object) -> None:
        raise RuntimeError("listener down")


def _format_record(record: logging.LogRecord) -> dict[str, Any]:
    from src.utils.product_events import ProductEventsFormatter

    return json.loads(ProductEventsFormatter().format(record))


def _product_records(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [record for record in records if record.name == "src.utils.product_events"]


def test_emit_product_event_fallback_filters_unknown_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.core.telemetry import emit_product_event

    with caplog.at_level(logging.INFO, logger="src.utils.product_events"):
        emit_product_event(None, "some_event", request_id="abc", secret_field="SEKRET")

    product_records = _product_records(caplog.records)
    assert len(product_records) == 1

    data = _format_record(product_records[0])
    assert data["event"] == "some_event"
    assert data["request_id"] == "abc"
    assert "secret_field" not in data


def test_emit_product_event_fallback_preserves_falsy_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.core.telemetry import emit_product_event

    with caplog.at_level(logging.INFO, logger="src.utils.product_events"):
        emit_product_event(None, "llm_completed", input_tokens=0, error_type=None)

    product_records = _product_records(caplog.records)
    assert len(product_records) == 1

    data = _format_record(product_records[0])
    assert data["event"] == "llm_completed"
    assert data["input_tokens"] == 0
    assert data["error_type"] is None


async def test_run_assistant_request_fail_opens_when_telemetry_listener_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.core.assistant import run_assistant_request
    from src.core.contracts import CoreDependencies

    deps = CoreDependencies(
        cache=_FakeCache(),
        embeddings=_FakeEmbeddings(),
        sparse_embeddings=_FakeSparseEmbeddings(),
        qdrant=_FakeQdrant(),
        telemetry=_FailingTelemetry(),
    )

    with caplog.at_level(logging.INFO):
        result = await run_assistant_request(
            "hello",
            collection="test",
            request_id="telemetry-fail-open",
            dependencies=deps,
        )

    assert result.request_id == "telemetry-fail-open"
    assert result.error_type == "dependency_failed"

    product_events = [
        getattr(record, "event", None)
        for record in _product_records(caplog.records)
        if hasattr(record, "event")
    ]
    assert "assistant_request_started" in product_events
    assert "assistant_request_completed" in product_events
    assert any(
        record.levelno == logging.WARNING
        and record.name == "src.core.telemetry"
        and "Telemetry listener failed" in record.getMessage()
        for record in caplog.records
    )
