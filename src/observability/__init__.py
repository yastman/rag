"""src.observability package — observability helpers.

Observability integration removed (#2844, #2969). Structured product logs
(src/utils/product_events.py) are the canonical observability path.

The only helpers kept here are genuine, non-tracing utilities
still used by the runtime: ``mask_pii`` (PII masking for safe payloads) and
``propagate_attributes`` (a no-op context manager preserved as a stable
context-propagation seam for callers).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from src.observability.scores import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_history_scores,
    write_scores,
)
from src.security.pii_redaction import PIIRedactor


_MAX_PII_TEXT_LENGTH = 4000
_pii_redactor = PIIRedactor()


def mask_pii(data: Any) -> Any:
    """Mask PII in arbitrary data (used when building safe payloads)."""
    return _pii_redactor.mask(data, max_length=_MAX_PII_TEXT_LENGTH)


@contextlib.contextmanager
def propagate_attributes(**kwargs: Any) -> Iterator[None]:
    """No-op context-propagation seam — tracing removed (#2844, #2969)."""
    yield


def observe(name: str = "", **_kw: Any) -> Any:
    """No-op @observe decorator — Langfuse removed (#2844, #2969).

    Accepts both ``@observe`` and ``@observe(name="...")`` usage.
    When called with a callable argument (bare decorator form), returns
    that callable unchanged. When called with keyword args (factory form),
    returns a pass-through decorator.
    """
    # ponytail: supports both @observe and @observe(name="x") — no framework needed
    if callable(name):
        return name  # bare @observe — name is actually the decorated function

    def _decorator(fn: Any) -> Any:
        return fn

    return _decorator


__all__ = [
    "compute_checkpointer_overhead_proxy_ms",
    "mask_pii",
    "observe",
    "propagate_attributes",
    "score",
    "write_history_scores",
    "write_scores",
]
