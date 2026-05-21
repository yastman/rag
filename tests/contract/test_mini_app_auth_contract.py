"""Contract tests for Telegram initData enforcement on Mini App endpoints (#1595).

These tests verify structural properties that must never regress:

  1. ``mini_app/api.py`` does NOT contain ``allow_origins=["*"]``.
  2. ``/api/start-expert`` and ``/api/phone`` handlers reference
     ``validate_init_data`` via the auth dependency.
  3. ``mini_app.auth.validate_init_data`` is actually imported in ``api.py``.
  4. The CORS middleware on the running app instance does not allow wildcard origins.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
API_FILE = REPO_ROOT / "mini_app" / "api.py"
AUTH_FILE = REPO_ROOT / "mini_app" / "auth.py"


# ---------------------------------------------------------------------------
# 1. No wildcard CORS in source code
# ---------------------------------------------------------------------------


def test_api_does_not_contain_wildcard_cors():
    """mini_app/api.py must not contain allow_origins=[\"*\"]."""
    source = API_FILE.read_text(encoding="utf-8")
    # Match the problematic wildcard pattern (handles whitespace variations)
    wildcard_pattern = re.compile(r'allow_origins\s*=\s*\[\s*["\']?\*["\']?\s*\]')
    assert not wildcard_pattern.search(source), (
        "mini_app/api.py still contains allow_origins=[\"*\"]. "
        "Set MINI_APP_ALLOWED_ORIGIN env var instead (#1595)."
    )


# ---------------------------------------------------------------------------
# 2. validate_init_data is imported in api.py
# ---------------------------------------------------------------------------


def test_validate_init_data_imported_in_api():
    """mini_app.auth.validate_init_data must be imported in mini_app/api.py."""
    source = API_FILE.read_text(encoding="utf-8")
    assert "validate_init_data" in source, (
        "mini_app/api.py must import validate_init_data from mini_app.auth (#1595). "
        "The function existed before but was never called by the API."
    )
    # Also confirm the import comes from mini_app.auth
    assert re.search(r"from mini_app\.auth import.*validate_init_data", source), (
        "validate_init_data must be imported from mini_app.auth in api.py (#1595)."
    )


# ---------------------------------------------------------------------------
# 3. Auth dependency referenced in both mutation handlers (AST/source check)
# ---------------------------------------------------------------------------


def test_start_expert_handler_references_auth_dependency():
    """start_expert handler must use get_validated_init_data dependency."""
    source = API_FILE.read_text(encoding="utf-8")
    # The dependency function must exist in the file
    assert "get_validated_init_data" in source, (
        "mini_app/api.py must define get_validated_init_data dependency (#1595)."
    )

    import ast

    tree = ast.parse(source)
    start_expert_node = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "start_expert"
        ):
            start_expert_node = node
            break

    assert start_expert_node is not None, "start_expert handler not found in api.py"

    # Check that get_validated_init_data appears as a Depends() default in the signature
    body_text = ast.unparse(start_expert_node)
    assert "get_validated_init_data" in body_text, (
        "start_expert handler must inject get_validated_init_data via Depends(). "
        "Found handler signature/body: " + body_text[:200]
    )


def test_phone_handler_references_auth_dependency():
    """phone handler must use get_validated_init_data dependency."""
    source = API_FILE.read_text(encoding="utf-8")

    import ast

    tree = ast.parse(source)
    phone_node = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "phone"
        ):
            phone_node = node
            break

    assert phone_node is not None, "phone handler not found in api.py"

    body_text = ast.unparse(phone_node)
    assert "get_validated_init_data" in body_text, (
        "phone handler must inject get_validated_init_data via Depends(). "
        "Found handler signature/body: " + body_text[:200]
    )


# ---------------------------------------------------------------------------
# 4. Runtime CORS check — no wildcard on the live app instance
# ---------------------------------------------------------------------------


def test_runtime_cors_not_wildcard():
    """The FastAPI app instance must not have allow_origins=['*'] in CORSMiddleware."""
    pytest.importorskip("fastapi")

    from fastapi.middleware.cors import CORSMiddleware

    from mini_app.api import app

    cors_middleware = None
    for mw in app.user_middleware:
        if hasattr(mw, "cls") and mw.cls is CORSMiddleware:
            cors_middleware = mw
            break
        if isinstance(mw, tuple) and len(mw) >= 1 and mw[0] is CORSMiddleware:
            cors_middleware = mw
            break

    assert cors_middleware is not None, "CORSMiddleware must be present on the app"

    if hasattr(cors_middleware, "kwargs"):
        cors_kwargs = cors_middleware.kwargs
    else:
        cors_kwargs = cors_middleware[-1] if isinstance(cors_middleware, tuple) else {}

    allow_origins = cors_kwargs.get("allow_origins", [])
    assert allow_origins != ["*"], (
        "CORSMiddleware allow_origins must not be ['*']. "
        f"Got: {allow_origins}. Set MINI_APP_ALLOWED_ORIGIN env var in production (#1595)."
    )


# ---------------------------------------------------------------------------
# 5. get_validated_init_data returns 401 (not 422) for missing header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_init_data_header_returns_401_not_422():
    """Missing X-Init-Data must produce 401, not the default FastAPI 422."""
    pytest.importorskip("fastapi")

    from unittest.mock import MagicMock

    from httpx import ASGITransport, AsyncClient

    import mini_app.api as api_mod
    from mini_app.api import app

    async def _noop_redis(_request=None):
        return MagicMock()

    app.dependency_overrides[api_mod.get_redis] = _noop_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            se_resp = await client.post(
                "/api/start-expert", json={"expert_id": "consultant"}
            )
            phone_resp = await client.post(
                "/api/phone", json={"phone": "+359888123456", "source": "t", "user_id": 1}
            )
    finally:
        app.dependency_overrides.pop(api_mod.get_redis, None)

    assert se_resp.status_code == 401, (
        f"/api/start-expert missing header → expected 401, got {se_resp.status_code}"
    )
    assert phone_resp.status_code == 401, (
        f"/api/phone missing header → expected 401, got {phone_resp.status_code}"
    )
