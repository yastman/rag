"""Parametrized behavior matrix for PII redaction.

One row per scenario: ``(case_id, query, expected, counts, flag)``, grouped by
phone, email, tax ID, passport, no-PII, mixed, edge, and pattern behavior. Test
IDs carry category and case (``test_pii_matrix[phone/plus-prefix]``) so failures
name the exact regression. ``None`` fields are not asserted (documentation-only
rows); counts map a pattern to its exact ``<pattern>_count`` (absent asserts 0).
Instance-level semantics and the zero-prefix phone/tax-id OR overlap stay outside
the matrix. ``# fmt: off`` keeps one scenario per table line (measured exception: formatter explosion would bury the matrix).
"""

import re

import pytest

from src.security.pii_redaction import PIIRedactor


Case = tuple[str, str, str | None, dict[str, int] | None, bool | None]


def unchanged(case_id: str, query: str) -> Case:
    return (case_id, query, query, None, False)


def assert_row(redactor: PIIRedactor, row: Case) -> None:
    case_id, query, expected, counts, flag = row
    redacted, metadata = redactor.redact_query(query)
    if expected is not None:
        assert redacted == expected, case_id
    for pattern, count in (counts or {}).items():
        assert metadata.get(f"{pattern}_count", 0) == count, f"{case_id}: {pattern}_count"
    if flag is not None:
        assert metadata["pii_redacted"] is flag, f"{case_id}: pii_redacted flag"


@pytest.fixture
def redactor() -> PIIRedactor:
    return PIIRedactor()


# fmt: off
PHONE_ROWS = [
    ("phone/plus-prefix", "Call me at +380501234567", "Call me at [PHONE]", {"phone": 1}, True),
    ("phone/local-zero", "My number is 0501234567", "My number is [PHONE]", {"phone": 1}, True),
    ("phone/multi", "Contact: +380501234567 or +380671234567 or 0991234567",
     "Contact: [PHONE] or [PHONE] or [PHONE]", {"phone": 3}, None),
    ("phone/in-sentence", "Подскажите статью, мой телефон +380501234567 для связи",
     "Подскажите статью, мой телефон [PHONE] для связи", None, True),
    ("phone/too-short", "The code is +3801234 which is too short", None, {"phone": 0}, None),
]

EMAIL_ROWS = [
    ("email/simple", "Send to user@example.com", "Send to [EMAIL]", {"email": 1}, True),
    ("email/dots", "Contact john.doe@company.org", "Contact [EMAIL]", {"email": 1}, None),
    ("email/plus-tag", "Email: user+tag@gmail.com", "Email: [EMAIL]", None, None),
    ("email/digits", "user123@test456.co.uk", "[EMAIL]", {"email": 1}, None),
    ("email/multi", "CC: alice@example.com and bob@company.org",
     "CC: [EMAIL] and [EMAIL]", {"email": 2}, None),
    ("email/subdomain", "admin@mail.example.co.uk", "[EMAIL]", {"email": 1}, None),
    ("email/underscore", "first_last@domain.com", "[EMAIL]", {"email": 1}, None),
]

TAX_ID_ROWS = [
    ("tax-id/ten-digits", "My tax ID is 1234567890", "My tax ID is [TAX_ID]", {"tax_id": 1}, True),
    ("tax-id/multi", "IDs: 1234567890 and 9876543210",
     "IDs: [TAX_ID] and [TAX_ID]", {"tax_id": 2}, None),
    ("tax-id/cyrillic", "РНОКПП громадянина: 1234567890",
     "РНОКПП громадянина: [TAX_ID]", None, None),
    ("tax-id/nine-digits", "Reference: 123456789", None, {"tax_id": 0}, None),
    ("tax-id/eleven-digits", "Number: 12345678901", None, None, None),  # documents current behavior
]

PASSPORT_ROWS = [
    ("passport/basic", "Passport: АБ123456", "Passport: [PASSPORT]", {"passport": 1}, True),
    ("passport/ukrainian", "Документ: ЇІ123456", "Документ: [PASSPORT]", {"passport": 1}, None),
    ("passport/multi", "Passports: АА111111 and ВВ222222",
     "Passports: [PASSPORT] and [PASSPORT]", {"passport": 2}, None),
    ("passport/in-sentence", "Номер паспорта СТ654321, виданий у Києві",
     "Номер паспорта [PASSPORT], виданий у Києві", None, None),
    ("passport/latin-letters", "Code: AB123456", None, {"passport": 0}, None),
]

NO_PII_ROWS = [
    unchanged("clean/english", "What is the penalty for theft in Ukraine?"),
    unchanged("clean/empty", ""),
    unchanged("clean/whitespace", "   \t\n   "),
    unchanged("clean/cyrillic-article", "Яка відповідальність за крадіжку згідно статті 185?"),
    unchanged("clean/article-number", "See article 185 paragraph 3"),
]

MIXED_ROWS = [
    ("mixed/phone-email-tax-id", "Contact: +380501234567, email@test.com, ID: 1234567890",
     "Contact: [PHONE], [EMAIL], ID: [TAX_ID]", {"phone": 1, "email": 1, "tax_id": 1}, None),
    ("mixed/all-four-types",
     "Person: АБ123456, tel +380501234567, user@mail.com, РНОКПП 1234567890",
     "Person: [PASSPORT], tel [PHONE], [EMAIL], РНОКПП [TAX_ID]",
     {"passport": 1, "phone": 1, "email": 1, "tax_id": 1}, True),
    ("mixed/text-around-pii", "Please help with question. My contact: +380501234567. Thanks!",
     "Please help with question. My contact: [PHONE]. Thanks!", None, None),
    ("mixed/newline-structure", "Email: user@test.com\nPhone: +380501234567\nID: 1234567890",
     "Email: [EMAIL]\nPhone: [PHONE]\nID: [TAX_ID]", None, None),
]

EDGE_ROWS = [
    ("edge/consecutive", "+380501234567+380671234567", "[PHONE][PHONE]", {"phone": 2}, None),
    ("edge/at-start", "+380501234567 is my number", "[PHONE] is my number", None, None),
    ("edge/at-end", "My email is user@example.com", "My email is [EMAIL]", None, None),
    ("edge/in-parentheses", "(+380501234567)", "([PHONE])", None, None),
    ("edge/emoji-context", "Контакт 📞: +380501234567", "Контакт 📞: [PHONE]", None, None),
    ("edge/repeat", "+380501234567 or again +380501234567",
     "[PHONE] or again [PHONE]", {"phone": 2}, None),
    ("edge/url-like", "Visit http://example.com/user@test for info",
     None, None, None),  # documents current behavior
    ("edge/long-query", "A" * 1000 + " +380501234567 " + "B" * 1000,
     "A" * 1000 + " [PHONE] " + "B" * 1000, {"phone": 1}, None),
    ("edge/counting", "Phones: +380111111111 +380222222222 +380333333333",
     "Phones: [PHONE] [PHONE] [PHONE]", {"phone": 3}, None),
]

PATTERN_ROWS = [
    ("pattern/plus-length", "Number: +380123456789", "Number: [PHONE]", {"phone": 1}, None),
    ("pattern/local-length", "Call 0501234567 for support",
     "Call [PHONE] for support", {"phone": 1}, None),
    ("pattern/tld-com", "user@example.com", "[EMAIL]", None, None),
    ("pattern/tld-org", "user@example.org", "[EMAIL]", None, None),
    ("pattern/tld-net", "user@example.net", "[EMAIL]", None, None),
    ("pattern/tld-io", "user@example.io", "[EMAIL]", None, None),
    ("pattern/tld-ua", "user@example.ua", "[EMAIL]", None, None),
    ("pattern/lowercase-cyrillic", "Document: аб123456", None, {"passport": 0}, None),
]

MATRIX_ROWS = PHONE_ROWS + EMAIL_ROWS + TAX_ID_ROWS + PASSPORT_ROWS + NO_PII_ROWS + MIXED_ROWS + EDGE_ROWS + PATTERN_ROWS
# fmt: on


@pytest.mark.parametrize("row", MATRIX_ROWS, ids=lambda row: row[0])
def test_pii_matrix(redactor: PIIRedactor, row: Case) -> None:
    assert_row(redactor, row)


def test_phone_tax_id_zero_prefix_overlap(redactor: PIIRedactor) -> None:
    """Zero-prefixed 10-digit numbers match phone (processed first) and/or tax_id."""
    _redacted, metadata = redactor.redact_query("ID: 0987654321")
    assert metadata["pii_redacted"] is True
    assert metadata.get("phone_count", 0) == 1 or metadata.get("tax_id_count", 0) == 1


class TestPIIRedactorInstance:
    """Instance-level behavior, kept outside the matrix (state semantics)."""

    def test_redactor_reusable(self) -> None:
        """Same redactor instance can be reused across queries."""
        redactor = PIIRedactor()
        result1, _ = redactor.redact_query("Email: a@b.com")
        result2, _ = redactor.redact_query("Phone: +380501234567")
        assert "[EMAIL]" in result1
        assert "[PHONE]" in result2

    def test_redactor_stateless(self) -> None:
        """Redactor does not maintain state between calls."""
        redactor = PIIRedactor()
        _, meta1 = redactor.redact_query("Email: a@b.com")
        _, meta2 = redactor.redact_query("No PII here")
        assert meta1["pii_redacted"] is True
        assert meta2["pii_redacted"] is False

    def test_multiple_redactor_instances(self) -> None:
        """Multiple instances behave identically."""
        redactor1 = PIIRedactor()
        redactor2 = PIIRedactor()
        result1, _ = redactor1.redact_query("test@example.com")
        result2, _ = redactor2.redact_query("test@example.com")
        assert result1 == result2 == "[EMAIL]"

    def test_patterns_are_compiled(self) -> None:
        """All patterns are pre-compiled regex objects."""
        redactor = PIIRedactor()
        for pattern_name, pattern in redactor.patterns.items():
            assert isinstance(pattern, re.Pattern), f"{pattern_name} is not compiled"
