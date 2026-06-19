"""Langfuse observability stubs — Langfuse removed (#2844).

All symbols are no-ops. The public API surface is preserved so existing
callers compile without changes. Return types use Any where callers do
attribute access (guarded by None checks at runtime).
"""

from __future__ import annotations

import contextlib
from typing import Any

from src.observability.langfuse_init import _reset_langfuse_init_state
from src.security.pii_redaction import PIIRedactor


_MAX_PII_TEXT_LENGTH = 4000
_pii_redactor = PIIRedactor()

_LANGFUSE_AVAILABLE = False
_LANGFUSE_IMPORT_ERROR: Exception | None = None


def _install_langfuse_warning_filters() -> None:
    """No-op stub — Langfuse removed (#2844)."""


_install_langfuse_warning_filters()


class Langfuse:
    """Stub placeholder — Langfuse removed (#2844)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Langfuse has been removed (#2844)")


def _real_observe(*args: Any, **kwargs: Any) -> Any:
    """No-op decorator factory."""

    def decorator(func: Any) -> Any:
        return func

    if args and callable(args[0]) and not kwargs:
        return args[0]
    return decorator


def _real_get_client() -> Any:
    return None


@contextlib.contextmanager  # type: ignore[misc]
def _real_propagate(**kwargs: Any) -> Any:
    yield


observe = _real_observe
get_client = _real_get_client
propagate_attributes = _real_propagate


def mask_pii(data: Any) -> Any:
    """Mask PII (still used for safe payloads)."""
    return _pii_redactor.mask(data, max_length=_MAX_PII_TEXT_LENGTH)


def initialize_langfuse(
    *,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    force: bool = False,
) -> Any:
    """No-op stub — Langfuse removed (#2844)."""
    return None


def get_langfuse_client() -> Any:
    """No-op stub — Langfuse removed (#2844)."""
    return None


def flush_langfuse() -> None:
    """No-op stub — Langfuse removed (#2844)."""


def _reset_langfuse_client_for_tests() -> None:
    """Reset module-level client cache (test-only helper)."""
    _reset_langfuse_init_state()


def traced_pipeline(
    *,
    session_id: str,
    user_id: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """No-op stub — Langfuse removed (#2844)."""
    return _real_propagate()


def make_lifecycle_session_id(family: str, key: str) -> str:
    """Build a stable session id string."""
    normalized = (key or "").strip().replace(" ", "-")
    return f"{family}-{normalized or 'unknown'}"


def update_lifecycle_trace(
    *,
    family: str,
    span_name: str,
    session_id: str,
    user_id: str,
    tags: list[str],
    metadata: dict[str, Any],
    trace_id: str | None = None,
) -> None:
    """No-op stub — Langfuse removed (#2844)."""


async def try_update_lifecycle_trace_async(
    *,
    family: str,
    span_name: str,
    session_id: str,
    user_id: str,
    tags: list[str],
    metadata: dict[str, Any],
    trace_id: str | None = None,
) -> None:
    """No-op stub — Langfuse removed (#2844)."""


def create_callback_handler(
    *,
    trace_context: Any | None = None,
) -> Any:
    """No-op stub — Langfuse removed (#2844)."""
    return None


def get_score_config_types() -> Any:
    """No-op stub — Langfuse removed (#2844)."""
    return None
