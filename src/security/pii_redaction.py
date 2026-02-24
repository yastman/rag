"""PII redaction and security guardrails for production RAG."""

import re
from typing import Any


class PIIRedactor:
    """
    Redact PII from queries and data before logging.

    Superset of patterns from both query redaction and Langfuse masking:
    - Ukrainian passport numbers
    - Tax IDs (РНОКПП): 10 digits (applied before user_id to avoid overlap)
    - Telegram user IDs: 9-10 digit standalone numbers
    - Phone numbers: international format (10-15 digits, optional +)
    - Email addresses
    """

    # Replacement tokens keyed by pattern name
    _REPLACEMENTS: dict[str, str] = {
        "passport": "[PASSPORT]",
        "tax_id": "[TAX_ID]",
        "user_id": "[USER_ID]",
        "phone": "[PHONE]",
        "email": "[EMAIL]",
    }

    def __init__(self) -> None:
        # Order matters: phone before tax_id so 0-prefixed Ukrainian local numbers (0XXXXXXXXX)
        # are matched as phone rather than tax_id; tax_id before user_id to avoid overlap on
        # 10-digit numbers without prefix.
        self.patterns: dict[str, re.Pattern[str]] = {
            "passport": re.compile(r"\b[А-ЯІЇЄҐ]{2}\d{6}\b"),
            "phone": re.compile(
                r"\+\d{9,14}|\b0\d{9}\b"
            ),  # + prefix international or 0 prefix Ukrainian local
            "tax_id": re.compile(r"\b\d{10}\b"),  # РНОКПП (10 digits, applied after phone)
            "user_id": re.compile(r"\b\d{9,10}\b"),  # Telegram user IDs (9-10 digits)
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        }

    def redact_query(self, query: str) -> tuple[str, dict[str, Any]]:
        """
        Redact PII from a user query string.

        Returns:
            (redacted_query, metadata_with_flags)
        """
        redacted = query
        pii_found: dict[str, Any] = {}

        for name, pattern in self.patterns.items():
            matches = pattern.findall(redacted)
            if matches:
                redacted = pattern.sub(self._REPLACEMENTS[name], redacted)
                pii_found[f"{name}_count"] = len(matches)

        return redacted, {"pii_redacted": len(pii_found) > 0, **pii_found}

    def mask(self, data: Any, *, max_length: int | None = None) -> Any:
        """
        Recursively mask PII in any data structure (str, dict, list).

        Args:
            data: Data to mask (string, dict, list, or other).
            max_length: If set, truncate strings longer than this value.

        Returns:
            Data with PII replaced and (optionally) long strings truncated.
        """
        if isinstance(data, str):
            redacted, _ = self.redact_query(data)
            if max_length is not None and len(redacted) > max_length:
                redacted = redacted[:max_length] + "... [TRUNCATED]"
            return redacted
        if isinstance(data, dict):
            return {k: self.mask(v, max_length=max_length) for k, v in data.items()}
        if isinstance(data, list):
            return [self.mask(item, max_length=max_length) for item in data]
        return data
