"""TDD tests for /api/log security hardening (issue ***REMOVED***1613).

RED phase: these tests FAIL against the original code.
GREEN phase: they pass after the Pydantic schema + structured logging fix.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

from mini_app.api import app


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Helpers
***REMOVED*** ---------------------------------------------------------------------------

def _log_handler_source() -> str:
    """Return the source of the remote_log handler function."""
    import mini_app.api as api_module

    src = inspect.getsource(api_module)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remote_log":
            return ast.get_source_segment(src, node) or ""
    raise RuntimeError("remote_log handler not found in mini_app.api")


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Schema validation tests
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_endpoint_rejects_unknown_level():
    """POST with level='CRITICAL' (not in allowed set) must return 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/log",
            json={"level": "CRITICAL", "message": "boom"},
        )
    assert resp.status_code == 422, (
        f"Expected 422 for unknown level, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_log_endpoint_rejects_oversized_message():
    """POST with message longer than 1000 chars must return 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/log",
            json={"level": "info", "message": "x" * 1001},
        )
    assert resp.status_code == 422, (
        f"Expected 422 for oversized message, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_log_endpoint_rejects_oversized_data():
    """POST with data value longer than 10000 chars must return 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/log",
            json={"level": "info", "message": "test", "data": {"k": "v" * 10001}},
        )
    assert resp.status_code == 422, (
        f"Expected 422 for oversized data, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_log_endpoint_accepts_valid_request():
    """Valid payload must return 200 with status ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/log",
            json={"level": "info", "message": "test"},
        )
    assert resp.status_code == 200, (
        f"Expected 200 for valid payload, got {resp.status_code}: {resp.text}"
    )
    assert resp.json().get("status") == "ok"


@pytest.mark.asyncio
async def test_log_endpoint_accepts_all_valid_levels():
    """All allowed levels (debug/info/warn/error) must return 200."""
    for level in ("debug", "info", "warn", "error"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/log",
                json={"level": level, "message": f"test {level}"},
            )
        assert resp.status_code == 200, (
            f"Expected 200 for level={level!r}, got {resp.status_code}: {resp.text}"
        )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Structured logging / no print() test
***REMOVED*** ---------------------------------------------------------------------------


def test_log_endpoint_uses_structured_logging_not_print():
    """The remote_log handler body must NOT contain a print() call.

    Uses AST inspection so we catch the literal source text, not monkey-patched
    runtime behaviour.
    """
    handler_src = _log_handler_source()
    tree = ast.parse(handler_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                pytest.fail(
                    "remote_log handler still uses print() — replace with logger.log()"
                )
            if isinstance(func, ast.Attribute) and func.attr == "print":
                pytest.fail(
                    "remote_log handler still uses *.print() — replace with logger.log()"
                )
