"""PII redaction and security guardrails for production RAG."""

import re


class PIIRedactor:
    """
    Redact PII from queries before logging to Langfuse/MLflow.

    Common PII patterns:
    - Ukrainian phone numbers: +380XXXXXXXXX
    - Email addresses
    - Tax IDs (РНОКПП): 10 digits
    - Passport numbers
    """

    def __init__(self):
        self.patterns = {
            "phone": re.compile(r"\+380\d{9}|\b0\d{9}\b"),
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "tax_id": re.compile(r"\b\d{10}\b"),  # РНОКПП
            "passport": re.compile(r"\b[А-ЯІЇЄҐ]{2}\d{6}\b"),
        }

    def redact_query(self, query: str) -> tuple[str, dict]:
        """
        Redact PII from query.

        Returns:
            (redacted_query, metadata_with_flags)
        """
        redacted = query
        pii_found = {}

        # Redact phone numbers
        phones = self.patterns["phone"].findall(query)
        if phones:
            redacted = self.patterns["phone"].sub("[PHONE]", redacted)
            pii_found["phone_count"] = len(phones)

        # Redact emails
        emails = self.patterns["email"].findall(query)
        if emails:
            redacted = self.patterns["email"].sub("[EMAIL]", redacted)
            pii_found["email_count"] = len(emails)

        # Redact tax IDs
        tax_ids = self.patterns["tax_id"].findall(query)
        if tax_ids:
            redacted = self.patterns["tax_id"].sub("[TAX_ID]", redacted)
            pii_found["tax_id_count"] = len(tax_ids)

        # Redact passports
        passports = self.patterns["passport"].findall(query)
        if passports:
            redacted = self.patterns["passport"].sub("[PASSPORT]", redacted)
            pii_found["passport_count"] = len(passports)

        metadata = {"pii_redacted": len(pii_found) > 0, **pii_found}

        return redacted, metadata
