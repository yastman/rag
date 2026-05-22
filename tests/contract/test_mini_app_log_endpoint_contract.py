"""Contract tests for /api/log endpoint security hardening (issue #1613).

These tests guard the structural invariants of the remote-log endpoint:
  - No raw print() in the handler body (AST walk).
  - The handler accepts a typed Pydantic model, not a bare ``dict``.
  - ``LogRequest`` declares ``max_length`` constraints on ``message``.

They are intentionally separate from the unit tests so that the RED/GREEN TDD
cycle is visible in CI history and so the contract remains enforceable
independently of the ASGI test client.

Contract 1 is AST-only and must run in the core environment without FastAPI.
Tests 2-4 introspect Pydantic v2 model metadata which is only computed at
class instantiation time, so they need the real ``mini_app.api`` module and
skip individually when the optional Mini App/FastAPI extra is not installed.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_type_hints

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MINI_APP_API = REPO_ROOT / "mini_app" / "api.py"


def _import_mini_app_api():
    pytest.importorskip("fastapi", reason="mini_app.api requires fastapi (mini-app extra)")
    import mini_app.api as api_module

    return api_module


def _get_remote_log_function():
    """Return the ``remote_log`` handler object from ``mini_app.api``."""
    api_module = _import_mini_app_api()

    func = getattr(api_module, "remote_log", None)
    assert func is not None, "remote_log not found in mini_app.api"
    return func


def _get_remote_log_ast_node() -> tuple[ast.AsyncFunctionDef, str]:
    """Return (AST node, full source) for the remote_log handler."""
    src = MINI_APP_API.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remote_log":
            return node, src
    raise AssertionError("remote_log async function not found in mini_app.api source")


# ---------------------------------------------------------------------------
# Contract 1: no print() in the handler body
# ---------------------------------------------------------------------------


def test_remote_log_handler_has_no_print_statement():
    """The remote_log handler must not contain any print() call.

    Using AST inspection so the check is immune to mock patching.
    """
    node, _ = _get_remote_log_ast_node()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id == "print":
                raise AssertionError(
                    "remote_log handler contains a bare print() call — "
                    "replace with structured logging (logger.log / logger.info / etc.)"
                )
            if isinstance(func, ast.Attribute) and func.attr == "print":
                raise AssertionError(
                    "remote_log handler contains a *.print() call — replace with structured logging"
                )


# ---------------------------------------------------------------------------
# Contract 2: handler accepts a Pydantic model, not a raw dict
# ---------------------------------------------------------------------------


def test_remote_log_handler_uses_pydantic_model_not_dict():
    """The remote_log handler's first parameter must be a Pydantic BaseModel subclass.

    Passing ``request: dict`` would bypass all Pydantic validation.
    """
    from pydantic import BaseModel

    func = _get_remote_log_function()
    hints = get_type_hints(func)

    # FastAPI injects ``request`` as the body parameter name.
    param_type = hints.get("request")
    assert param_type is not None, "remote_log has no 'request' parameter type annotation"
    assert param_type is not dict, (
        f"remote_log 'request' parameter must be a Pydantic model, not dict — got {param_type!r}"
    )
    assert issubclass(param_type, BaseModel), (
        f"remote_log 'request' parameter must subclass pydantic.BaseModel — got {param_type!r}"
    )


# ---------------------------------------------------------------------------
# Contract 3: LogRequest has max_length on message
# ---------------------------------------------------------------------------


def test_log_request_model_has_max_length_on_message():
    """LogRequest.message must declare a max_length constraint."""
    LogRequest = _import_mini_app_api().LogRequest

    field_info = LogRequest.model_fields.get("message")
    assert field_info is not None, "LogRequest has no 'message' field"

    # Pydantic v2 stores constraints in field_info.metadata
    has_max_length = False
    for meta in getattr(field_info, "metadata", []):
        # pydantic._internal.known_annotated_metadata.MaxLen
        if hasattr(meta, "max_length") and meta.max_length is not None:
            has_max_length = True
            break

    assert has_max_length, (
        "LogRequest.message must have a max_length constraint via "
        "pydantic.Field(max_length=...) or Annotated[str, MaxLen(...)]"
    )


# ---------------------------------------------------------------------------
# Contract 4: LogRequest level field is a Literal with allowed values only
# ---------------------------------------------------------------------------


def test_log_request_model_restricts_level_to_known_values():
    """LogRequest.level must be a Literal with only the four allowed values."""
    import typing
    from typing import Literal

    LogRequest = _import_mini_app_api().LogRequest

    field_info = LogRequest.model_fields.get("level")
    assert field_info is not None, "LogRequest has no 'level' field"

    annotation = field_info.annotation
    origin = getattr(annotation, "__origin__", None)
    assert origin is Literal or origin is typing.Literal, (  # type: ignore[comparison-overlap]
        f"LogRequest.level must be a Literal type, got {annotation!r}"
    )

    allowed = set(annotation.__args__)
    assert allowed == {"debug", "info", "warn", "error"}, (
        f"LogRequest.level Literal must contain exactly {{'debug','info','warn','error'}}, "
        f"got {allowed!r}"
    )
