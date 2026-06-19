"""Langfuse init stubs — Langfuse removed (#2844).

Module-level state and accessor functions are kept so langfuse_client.py
and contract tests that call _reset_langfuse_client_for_tests() still work.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.observability.bootstrap import (
    disable_otel_exporter as _disable_otel_exporter,
)


logger = logging.getLogger(__name__)

_langfuse_client: Any = None
_langfuse_init_attempted = False
_langfuse_endpoint_warned = False


def get_langfuse_init_client() -> Any:
    """Return the current initialized client — always None after #2844."""
    return None


def initialize_langfuse(
    *,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    force: bool = False,
    _langfuse_cls: Any = None,
    _mask_fn: Callable[..., Any] | None = None,
) -> Any:
    """No-op stub — Langfuse removed (#2844)."""
    global _langfuse_init_attempted
    _disable_otel_exporter()
    _langfuse_init_attempted = True
    return None


def _reset_langfuse_init_state() -> None:
    """Reset module-level init state (test-only helper)."""
    global _langfuse_client, _langfuse_init_attempted, _langfuse_endpoint_warned
    _langfuse_client = None
    _langfuse_init_attempted = False
    _langfuse_endpoint_warned = False
