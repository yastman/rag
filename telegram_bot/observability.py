# telegram_bot/observability.py
"""Langfuse observability with PII masking.

2026 best practice: "Log everything, but with masking enabled first."
All inputs/outputs go through PII redaction before Langfuse.
"""

import re
from typing import Any

from langfuse import Langfuse


def mask_pii(data: Any) -> Any:
    """Mask PII before sending to Langfuse.

    Applied to all inputs/outputs/metadata automatically.

    Masks:
    - Telegram user IDs (9-10 digits)
    - Phone numbers (10-15 digits with optional +)
    - Email addresses
    - Long texts (>500 chars truncated)
    """
    if isinstance(data, str):
        # Mask Telegram user IDs (9-10 digits not part of larger number)
        data = re.sub(r"\b\d{9,10}\b", "[USER_ID]", data)
        # Mask phone numbers
        data = re.sub(r"\+?\d{10,15}", "[PHONE]", data)
        # Mask emails
        data = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "[EMAIL]", data)
        # Truncate long texts
        if len(data) > 500:
            data = data[:500] + "... [TRUNCATED]"
        return data
    if isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_pii(item) for item in data]
    return data


def get_langfuse_client() -> Langfuse:
    """Get Langfuse client with PII masking enabled.

    Returns:
        Langfuse client configured with:
        - mask_pii callback for all data
        - Batch size 50, flush interval 5s
    """
    return Langfuse(
        mask=mask_pii,
        flush_at=50,
        flush_interval=5,
    )
