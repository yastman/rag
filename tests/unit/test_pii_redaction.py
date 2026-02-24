import pytest

from src.security.pii_redaction import PIIRedactor


@pytest.fixture
def redactor():
    return PIIRedactor()


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
