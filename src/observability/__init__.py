"""src.observability package — observability helpers.

Observability integration removed (#2844, #2969). Structured product logs
(src/utils/product_events.py) are the canonical observability path.

The only helpers kept here are genuine, non-tracing utilities
still used by the runtime: ``mask_pii`` (PII masking for safe payloads) and
the no-op scores stubs (score/write_scores/write_history_scores).

No-op shims removed (card_9967cd60fe32):
  observe, traced_pipeline, get_client, propagate_attributes — confirmed 0
  prod callers after card_70130e28eadd.
"""

from __future__ import annotations

from typing import Any

from src.observability.scores import (
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


__all__ = [
    "mask_pii",
    "score",
    "write_history_scores",
    "write_scores",
]
