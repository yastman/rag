import pytest

from src.security.pii_redaction import BudgetGuard, PIIRedactor


@pytest.fixture
def redactor():
    return PIIRedactor()


@pytest.fixture
def budget():
    return BudgetGuard()


class TestPIIRedactor:
    def test_redact_phone(self, redactor):
        query = "Call me at +380501234567 regarding the case."
        redacted, meta = redactor.redact_query(query)

        assert "[PHONE]" in redacted
        assert "+380501234567" not in redacted
        assert meta["pii_redacted"] is True
        assert meta["phone_count"] == 1

    def test_redact_email(self, redactor):
        query = "Email us at support@example.com immediately."
        redacted, meta = redactor.redact_query(query)

        assert "[EMAIL]" in redacted
        assert "support@example.com" not in redacted
        assert meta["pii_redacted"] is True
        assert meta["email_count"] == 1

    def test_redact_tax_id(self, redactor):
        query = "My tax ID is 1234567890."
        redacted, meta = redactor.redact_query(query)

        assert "[TAX_ID]" in redacted
        assert "1234567890" not in redacted
        assert meta["pii_redacted"] is True
        assert meta["tax_id_count"] == 1

    def test_no_pii(self, redactor):
        query = "Hello world"
        redacted, meta = redactor.redact_query(query)

        assert redacted == query
        assert meta["pii_redacted"] is False


class TestBudgetGuard:
    def test_daily_limit_ok(self, budget):
        allowed, msg = budget.check_budget(1.0)
        assert allowed is True
        assert msg is None

    def test_daily_limit_exceeded(self, budget):
        budget.current_spend["daily"] = 9.99
        allowed, msg = budget.check_budget(0.10)

        assert allowed is False
        assert "Daily budget exceeded" in msg

    def test_alert_threshold(self, budget):
        budget.current_spend["daily"] = 8.50  # 85% of $10
        allowed, msg = budget.check_budget(0.10)

        assert allowed is True
        assert "⚠️" in msg
        assert "Daily budget at" in msg

    def test_record_spend(self, budget):
        budget.record_spend(1.50)
        assert budget.current_spend["daily"] == 1.50
        assert budget.current_spend["monthly"] == 1.50

    def test_reset_daily(self, budget):
        budget.current_spend["daily"] = 5.0
        budget.current_spend["monthly"] = 100.0

        budget.reset_daily()

        assert budget.current_spend["daily"] == 0.0
        assert budget.current_spend["monthly"] == 100.0
