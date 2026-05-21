"""TDD tests for /api/log security hardening (issue #1613).

RED phase: these tests FAIL against the original code.
GREEN phase: they pass after the Pydantic schema + structured logging fix.
"""

from __future__ import annotations

import ast
import inspect
from unittest.mock import patch

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

from mini_app.api import app


_AUTH_HEADERS = {"X-Init-Data": "test-init-data"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_handler_source() -> str:
    """Return the source of the remote_log handler function."""
    import mini_app.api as api_module

    src = inspect.getsource(api_module)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remote_log":
            return ast.get_source_segment(src, node) or ""
    raise RuntimeError("remote_log handler not found in mini_app.api")


async def _post_log(json: dict, headers: dict[str, str] | None = None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/log", json=json, headers=headers)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


async def test_log_endpoint_requires_init_data_header():
    """POST /api/log without X-Init-Data must fail closed with 401."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        resp = await _post_log(json={"level": "info", "message": "test"})

    assert resp.status_code == 401, (
        f"Expected 401 when X-Init-Data is missing, got {resp.status_code}: {resp.text}"
    )


async def test_log_endpoint_rejects_invalid_init_data():
    """POST /api/log with invalid signed initData must fail with 401."""
    with patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"},
        clear=False,
    ):
        resp = await _post_log(
            json={"level": "info", "message": "test"},
            headers={"X-Init-Data": "auth_date=1&hash=invalid"},
        )

    assert resp.status_code == 401, (
        f"Expected 401 for invalid initData, got {resp.status_code}: {resp.text}"
    )


async def test_log_endpoint_rejects_unknown_level():
    """POST with level='CRITICAL' (not in allowed set) must return 422."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        resp = await _post_log(
            json={"level": "CRITICAL", "message": "boom"},
            headers=_AUTH_HEADERS,
        )
    assert resp.status_code == 422, (
        f"Expected 422 for unknown level, got {resp.status_code}: {resp.text}"
    )


async def test_log_endpoint_rejects_oversized_message():
    """POST with message longer than 1000 chars must return 422."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        resp = await _post_log(
            json={"level": "info", "message": "x" * 1001},
            headers=_AUTH_HEADERS,
        )
    assert resp.status_code == 422, (
        f"Expected 422 for oversized message, got {resp.status_code}: {resp.text}"
    )


async def test_log_endpoint_rejects_oversized_data():
    """POST with data value longer than 10000 chars must return 422."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        resp = await _post_log(
            json={"level": "info", "message": "test", "data": {"k": "v" * 10001}},
            headers=_AUTH_HEADERS,
        )
    assert resp.status_code == 422, (
        f"Expected 422 for oversized data, got {resp.status_code}: {resp.text}"
    )


async def test_log_endpoint_accepts_valid_request():
    """Valid payload must return 200 with status ok."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        resp = await _post_log(
            json={"level": "info", "message": "test"},
            headers=_AUTH_HEADERS,
        )
    assert resp.status_code == 200, (
        f"Expected 200 for valid payload, got {resp.status_code}: {resp.text}"
    )
    assert resp.json().get("status") == "ok"


async def test_log_endpoint_accepts_all_valid_levels():
    """All allowed levels (debug/info/warn/error) must return 200."""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        for level in ("debug", "info", "warn", "error"):
            resp = await _post_log(
                json={"level": level, "message": f"test {level}"},
                headers=_AUTH_HEADERS,
            )
            assert resp.status_code == 200, (
                f"Expected 200 for level={level!r}, got {resp.status_code}: {resp.text}"
            )


# ---------------------------------------------------------------------------
# Structured logging / no print() test
# ---------------------------------------------------------------------------


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
                pytest.fail("remote_log handler still uses print() — replace with logger.log()")
            if isinstance(func, ast.Attribute) and func.attr == "print":
                pytest.fail("remote_log handler still uses *.print() — replace with logger.log()")
