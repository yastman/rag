"""src.observability package — observability helpers.

Langfuse removed (#2844, #2969). Structured product logs
(src/utils/product_events.py) are the canonical observability path.

The only Langfuse-era utilities kept here are genuine, non-Langfuse helpers
still used by the runtime: ``mask_pii`` (PII masking for safe payloads) and
``propagate_attributes`` (a no-op context manager preserved as a stable
context-propagation seam for callers).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from src.observability.bootstrap import disable_otel_exporter, is_endpoint_reachable
from src.observability.safe_payloads import build_safe_input_payload, build_safe_output_payload
from src.observability.scores import (
    compute_checkpointer_overhead_proxy_ms,
    score,
    write_history_scores,
    write_langfuse_scores,
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
    """No-op context-propagation seam — Langfuse removed (#2844, #2969)."""
    yield


# Legacy aliases
_disable_otel_exporter = disable_otel_exporter
_is_endpoint_reachable = is_endpoint_reachable

__all__ = [
    "build_safe_input_payload",
    "build_safe_output_payload",
    "compute_checkpointer_overhead_proxy_ms",
    "disable_otel_exporter",
    "is_endpoint_reachable",
    "mask_pii",
    "propagate_attributes",
    "score",
    "write_history_scores",
    "write_langfuse_scores",
    "write_scores",
]
