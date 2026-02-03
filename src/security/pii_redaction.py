"""PII redaction and security guardrails for production RAG."""

import re

from langfuse import get_client


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


class BudgetGuard:
    """
    Budget limits for LLM providers.

    Prevents runaway costs in production.
    """

    def __init__(self):
        self.limits = {
            "daily": 10.0,  # $10/day
            "monthly": 300.0,  # $300/month
        }

        self.current_spend = {
            "daily": 0.0,
            "monthly": 0.0,
        }

        self.alert_threshold = 0.80  # Alert at 80%

    def check_budget(self, estimated_cost: float) -> tuple[bool, str | None]:
        """
        Check if request would exceed budget.

        Returns:
            (allowed, warning_message)
        """

        # Check daily limit
        if self.current_spend["daily"] + estimated_cost > self.limits["daily"]:
            return (
                False,
                f"Daily budget exceeded: ${self.current_spend['daily']:.2f} / ${self.limits['daily']:.2f}",
            )

        # Check monthly limit
        if self.current_spend["monthly"] + estimated_cost > self.limits["monthly"]:
            return (
                False,
                f"Monthly budget exceeded: ${self.current_spend['monthly']:.2f} / ${self.limits['monthly']:.2f}",
            )

        # Check alert threshold
        daily_pct = (self.current_spend["daily"] + estimated_cost) / self.limits["daily"]
        if daily_pct >= self.alert_threshold:
            return (
                True,
                f"⚠️  Daily budget at {daily_pct:.0%}: ${self.current_spend['daily']:.2f} / ${self.limits['daily']:.2f}",
            )

        return True, None

    def record_spend(self, cost: float):
        """Record actual spend."""
        self.current_spend["daily"] += cost
        self.current_spend["monthly"] += cost

    def reset_daily(self):
        """Reset daily counter (run at midnight)."""
        self.current_spend["daily"] = 0.0


# Usage in RAG pipeline
class SecureRAGPipeline:
    """RAG Pipeline with PII redaction and budget guards."""

    def __init__(self):
        self.pii_redactor = PIIRedactor()
        self.budget_guard = BudgetGuard()

    async def query(self, query: str, user_id: str):
        """Query with security checks."""

        # 1. Redact PII
        redacted_query, pii_metadata = self.pii_redactor.redact_query(query)

        if pii_metadata["pii_redacted"]:
            print(f"⚠️  PII detected and redacted: {pii_metadata}")

        # 2. Check budget
        estimated_cost = 0.001  # Estimate based on query length
        allowed, warning = self.budget_guard.check_budget(estimated_cost)

        if not allowed:
            raise Exception(f"🚫 Budget limit reached: {warning}")

        if warning:
            print(warning)

        # 3. Execute query (with redacted version logged to Langfuse)
        langfuse = get_client()
        langfuse.update_current_trace(
            input={"query": redacted_query},  # Redacted version
            metadata={
                **pii_metadata,
                "user_id": user_id,
                "budget_check": "passed",
            },
        )

        # ... execute RAG pipeline ...

        # 4. Record actual cost
        actual_cost = 0.0008  # From LLM response
        self.budget_guard.record_spend(actual_cost)

        return {"results": []}  # Placeholder
