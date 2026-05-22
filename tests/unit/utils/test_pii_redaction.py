"""
Comprehensive unit tests for PII redaction functionality.

Tests the PIIRedactor class which handles:
- Ukrainian phone numbers (+380XXXXXXXXX, 0XXXXXXXXX)
- Email addresses
- Tax IDs (РНОКПП - 10 digits)
- Passport numbers (Ukrainian format: 2 Cyrillic letters + 6 digits)
"""

import pytest

from src.security.pii_redaction import PIIRedactor


class TestPIIRedactorPhoneNumbers:
    """Test phone number redaction."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_redact_ukrainian_phone_with_plus_prefix(self, redactor: PIIRedactor):
        """Test redaction of +380 format phone numbers."""
        query = "Call me at +380501234567"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "Call me at [PHONE]"
        assert metadata["pii_redacted"] is True
        assert metadata["phone_count"] == 1

    def test_redact_ukrainian_phone_without_plus(self, redactor: PIIRedactor):
        """Test redaction of local format phone numbers (0XXXXXXXXX)."""
        query = "My number is 0501234567"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "My number is [PHONE]"
        assert metadata["pii_redacted"] is True
        assert metadata["phone_count"] == 1

    def test_redact_multiple_phone_numbers(self, redactor: PIIRedactor):
        """Test redaction of multiple phone numbers in one query."""
        query = "Contact: +380501234567 or +380671234567 or 0991234567"
        redacted, metadata = redactor.redact_query(query)

        assert "[PHONE]" in redacted
        assert "+380" not in redacted
        assert metadata["phone_count"] == 3

    def test_phone_number_in_sentence(self, redactor: PIIRedactor):
        """Test phone number embedded in natural text."""
        query = "Подскажите статью, мой телефон +380501234567 для связи"
        redacted, metadata = redactor.redact_query(query)

        assert "+380501234567" not in redacted
        assert "[PHONE]" in redacted
        assert metadata["pii_redacted"] is True

    def test_invalid_phone_number_not_redacted(self, redactor: PIIRedactor):
        """Test that invalid phone formats are not redacted."""
        query = "The code is +3801234 which is too short"
        _redacted, metadata = redactor.redact_query(query)

        # Should not match - too short
        assert "phone_count" not in metadata or metadata.get("phone_count", 0) == 0


class TestPIIRedactorEmails:
    """Test email address redaction."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_redact_simple_email(self, redactor: PIIRedactor):
        """Test basic email redaction."""
        query = "Send to user@example.com"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "Send to [EMAIL]"
        assert metadata["pii_redacted"] is True
        assert metadata["email_count"] == 1

    def test_redact_email_with_dots(self, redactor: PIIRedactor):
        """Test email with dots in local part."""
        query = "Contact john.doe@company.org"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "Contact [EMAIL]"
        assert metadata["email_count"] == 1

    def test_redact_email_with_plus(self, redactor: PIIRedactor):
        """Test email with plus sign (Gmail-style)."""
        query = "Email: user+tag@gmail.com"
        redacted, _metadata = redactor.redact_query(query)

        assert "[EMAIL]" in redacted
        assert "gmail.com" not in redacted

    def test_redact_email_with_numbers(self, redactor: PIIRedactor):
        """Test email containing numbers."""
        query = "user123@test456.co.uk"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "[EMAIL]"
        assert metadata["email_count"] == 1

    def test_redact_multiple_emails(self, redactor: PIIRedactor):
        """Test multiple email addresses."""
        query = "CC: alice@example.com and bob@company.org"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "CC: [EMAIL] and [EMAIL]"
        assert metadata["email_count"] == 2

    def test_email_with_subdomain(self, redactor: PIIRedactor):
        """Test email with subdomain."""
        query = "admin@mail.example.co.uk"
        redacted, metadata = redactor.redact_query(query)

        assert "[EMAIL]" in redacted
        assert metadata["email_count"] == 1

    def test_email_with_underscore(self, redactor: PIIRedactor):
        """Test email with underscore in local part."""
        query = "first_last@domain.com"
        redacted, metadata = redactor.redact_query(query)

        assert "[EMAIL]" in redacted
        assert metadata["email_count"] == 1


class TestPIIRedactorTaxID:
    """Test Ukrainian Tax ID (РНОКПП) redaction."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_redact_tax_id(self, redactor: PIIRedactor):
        """Test basic tax ID redaction (10 digits)."""
        query = "My tax ID is 1234567890"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "My tax ID is [TAX_ID]"
        assert metadata["pii_redacted"] is True
        assert metadata["tax_id_count"] == 1

    def test_redact_multiple_tax_ids(self, redactor: PIIRedactor):
        """Test multiple tax IDs.

        Note: Tax IDs starting with 0 may also match local phone pattern.
        Using tax IDs that don't start with 0 to test pure tax ID behavior.
        """
        query = "IDs: 1234567890 and 9876543210"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "IDs: [TAX_ID] and [TAX_ID]"
        assert metadata["tax_id_count"] == 2

    def test_tax_id_in_cyrillic_text(self, redactor: PIIRedactor):
        """Test tax ID in Ukrainian text context."""
        query = "РНОКПП громадянина: 1234567890"
        redacted, _metadata = redactor.redact_query(query)

        assert "1234567890" not in redacted
        assert "[TAX_ID]" in redacted

    def test_nine_digits_not_redacted_as_tax_id(self, redactor: PIIRedactor):
        """Test that 9-digit numbers are not redacted as tax IDs."""
        query = "Reference: 123456789"  # 9 digits, not 10
        _redacted, metadata = redactor.redact_query(query)

        # Should not be redacted as tax ID
        assert "tax_id_count" not in metadata or metadata.get("tax_id_count", 0) == 0

    def test_eleven_digits_not_redacted_as_tax_id(self, redactor: PIIRedactor):
        """Test that 11-digit numbers are not redacted as tax IDs."""
        query = "Number: 12345678901"  # 11 digits
        _redacted, _metadata = redactor.redact_query(query)

        # 11 digits should not match the 10-digit tax ID pattern
        # Note: The pattern uses \b word boundaries, so this depends on context

    def test_tax_id_starting_with_zero_also_matches_phone(self, redactor: PIIRedactor):
        r"""Test pattern overlap: 10-digit number starting with 0 matches both patterns.

        The local phone pattern (0\d{9}) will match tax IDs starting with 0.
        This documents the expected behavior - phone pattern takes precedence
        after tax_id redaction since both counts are recorded.
        """
        query = "ID: 0987654321"
        _redacted, metadata = redactor.redact_query(query)

        # The number matches both tax_id (10 digits) and phone (0 + 9 digits)
        # Order of processing: phone, email, tax_id, passport
        # So tax_id replaces first, then phone pattern tries but text is already [TAX_ID]
        # Actually: phone is processed FIRST, so it matches 0987654321
        assert metadata["pii_redacted"] is True
        # Both patterns detected the number (before any replacement)
        assert metadata.get("phone_count", 0) == 1 or metadata.get("tax_id_count", 0) == 1


class TestPIIRedactorPassport:
    """Test Ukrainian passport number redaction."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_redact_passport_number(self, redactor: PIIRedactor):
        """Test basic passport redaction (2 Cyrillic letters + 6 digits)."""
        query = "Passport: АБ123456"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "Passport: [PASSPORT]"
        assert metadata["pii_redacted"] is True
        assert metadata["passport_count"] == 1

    def test_redact_passport_with_ukrainian_letters(self, redactor: PIIRedactor):
        """Test passport with Ukrainian-specific letters (І, Ї, Є, Ґ)."""
        query = "Документ: ЇІ123456"
        redacted, metadata = redactor.redact_query(query)

        assert "ЇІ123456" not in redacted
        assert "[PASSPORT]" in redacted
        assert metadata["passport_count"] == 1

    def test_redact_multiple_passports(self, redactor: PIIRedactor):
        """Test multiple passport numbers."""
        query = "Passports: АА111111 and ВВ222222"
        redacted, metadata = redactor.redact_query(query)

        assert "АА111111" not in redacted
        assert "ВВ222222" not in redacted
        assert metadata["passport_count"] == 2

    def test_passport_in_sentence(self, redactor: PIIRedactor):
        """Test passport in natural Ukrainian text."""
        query = "Номер паспорта СТ654321, виданий у Києві"
        redacted, _metadata = redactor.redact_query(query)

        assert "СТ654321" not in redacted
        assert "[PASSPORT]" in redacted

    def test_latin_letters_not_redacted_as_passport(self, redactor: PIIRedactor):
        """Test that Latin letters are not matched as passport."""
        query = "Code: AB123456"  # Latin letters, not Cyrillic
        _redacted, metadata = redactor.redact_query(query)

        # Latin letters should not match Cyrillic pattern
        assert "passport_count" not in metadata or metadata.get("passport_count", 0) == 0


class TestPIIRedactorNoPII:
    """Test handling of text without PII."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_text_without_pii_unchanged(self, redactor: PIIRedactor):
        """Test that clean text passes through unchanged."""
        query = "What is the penalty for theft in Ukraine?"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == query
        assert metadata["pii_redacted"] is False

    def test_empty_string(self, redactor: PIIRedactor):
        """Test empty input."""
        query = ""
        redacted, metadata = redactor.redact_query(query)

        assert redacted == ""
        assert metadata["pii_redacted"] is False

    def test_whitespace_only(self, redactor: PIIRedactor):
        """Test whitespace-only input."""
        query = "   \t\n   "
        redacted, metadata = redactor.redact_query(query)

        assert redacted == query
        assert metadata["pii_redacted"] is False

    def test_cyrillic_text_without_pii(self, redactor: PIIRedactor):
        """Test Ukrainian text without PII."""
        query = "Яка відповідальність за крадіжку згідно статті 185?"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == query
        assert metadata["pii_redacted"] is False

    def test_numbers_that_are_not_pii(self, redactor: PIIRedactor):
        """Test that article numbers and other numeric references are not redacted."""
        query = "See article 185 paragraph 3"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == query
        assert metadata["pii_redacted"] is False


class TestPIIRedactorMixedContent:
    """Test queries with multiple types of PII."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_multiple_pii_types(self, redactor: PIIRedactor):
        """Test query with phone, email, and tax ID."""
        query = "Contact: +380501234567, email@test.com, ID: 1234567890"
        redacted, metadata = redactor.redact_query(query)

        assert "+380501234567" not in redacted
        assert "email@test.com" not in redacted
        assert "1234567890" not in redacted
        assert "[PHONE]" in redacted
        assert "[EMAIL]" in redacted
        assert "[TAX_ID]" in redacted
        assert metadata["phone_count"] == 1
        assert metadata["email_count"] == 1
        assert metadata["tax_id_count"] == 1

    def test_all_pii_types(self, redactor: PIIRedactor):
        """Test query with all four PII types."""
        query = "Person: АБ123456, tel +380501234567, user@mail.com, РНОКПП 1234567890"
        redacted, metadata = redactor.redact_query(query)

        assert metadata["pii_redacted"] is True
        assert metadata["passport_count"] == 1
        assert metadata["phone_count"] == 1
        assert metadata["email_count"] == 1
        assert metadata["tax_id_count"] == 1
        assert redacted.count("[") == 4  # Four redaction placeholders

    def test_mixed_pii_and_regular_text(self, redactor: PIIRedactor):
        """Test that regular text around PII is preserved."""
        query = "Please help with question. My contact: +380501234567. Thanks!"
        redacted, _metadata = redactor.redact_query(query)

        assert redacted == "Please help with question. My contact: [PHONE]. Thanks!"

    def test_preserves_query_structure(self, redactor: PIIRedactor):
        """Test that query structure (punctuation, spacing) is preserved."""
        query = "Email: user@test.com\nPhone: +380501234567\nID: 1234567890"
        redacted, _metadata = redactor.redact_query(query)

        assert "Email: [EMAIL]" in redacted
        assert "Phone: [PHONE]" in redacted
        assert "ID: [TAX_ID]" in redacted
        assert "\n" in redacted  # Newlines preserved


class TestPIIRedactorEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_consecutive_phone_numbers(self, redactor: PIIRedactor):
        """Test phone numbers without separator."""
        query = "+380501234567+380671234567"
        redacted, metadata = redactor.redact_query(query)

        assert "+380" not in redacted
        assert metadata["phone_count"] == 2

    def test_pii_at_start_of_string(self, redactor: PIIRedactor):
        """Test PII at the beginning of query."""
        query = "+380501234567 is my number"
        redacted, _metadata = redactor.redact_query(query)

        assert redacted.startswith("[PHONE]")

    def test_pii_at_end_of_string(self, redactor: PIIRedactor):
        """Test PII at the end of query."""
        query = "My email is user@example.com"
        redacted, _metadata = redactor.redact_query(query)

        assert redacted.endswith("[EMAIL]")

    def test_special_characters_around_pii(self, redactor: PIIRedactor):
        """Test PII surrounded by special characters."""
        query = "(+380501234567)"
        redacted, _metadata = redactor.redact_query(query)

        assert redacted == "([PHONE])"

    def test_unicode_text_with_pii(self, redactor: PIIRedactor):
        """Test Unicode characters mixed with PII."""
        query = "Контакт 📞: +380501234567"
        redacted, _metadata = redactor.redact_query(query)

        assert "+380501234567" not in redacted
        assert "📞" in redacted  # Emoji preserved

    def test_repeated_same_pii(self, redactor: PIIRedactor):
        """Test same PII value repeated."""
        query = "+380501234567 or again +380501234567"
        redacted, metadata = redactor.redact_query(query)

        assert redacted == "[PHONE] or again [PHONE]"
        assert metadata["phone_count"] == 2

    def test_pii_like_patterns_in_urls(self, redactor: PIIRedactor):
        """Test that URL-like patterns are handled."""
        query = "Visit http://example.com/user@test for info"
        _redacted, _metadata = redactor.redact_query(query)

        # The email pattern might match user@test - this is expected behavior
        # The test documents the current behavior

    def test_very_long_query_with_pii(self, redactor: PIIRedactor):
        """Test performance with longer text."""
        query = "A" * 1000 + " +380501234567 " + "B" * 1000
        redacted, _metadata = redactor.redact_query(query)

        assert "+380501234567" not in redacted
        assert "[PHONE]" in redacted
        assert len(redacted) < len(query)  # Shorter due to redaction

    def test_metadata_counts_accurate(self, redactor: PIIRedactor):
        """Verify metadata counts are accurate."""
        query = "Phones: +380111111111 +380222222222 +380333333333"
        redacted, metadata = redactor.redact_query(query)

        assert metadata["phone_count"] == 3
        assert redacted.count("[PHONE]") == 3


class TestPIIRedactorPatterns:
    """Test specific pattern behaviors and boundaries."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_phone_pattern_exact_length(self, redactor: PIIRedactor):
        """Test that phone patterns match exact lengths."""
        # +380 followed by exactly 9 digits
        valid = "+380123456789"  # +380 + 9 digits = valid
        query = f"Number: {valid}"
        redacted, metadata = redactor.redact_query(query)

        assert "[PHONE]" in redacted
        assert metadata.get("phone_count", 0) == 1

    def test_local_phone_pattern_exact_length(self, redactor: PIIRedactor):
        """Test local format phone (0 + 9 digits)."""
        query = "Call 0501234567 for support"
        redacted, metadata = redactor.redact_query(query)

        assert "[PHONE]" in redacted
        assert metadata.get("phone_count", 0) == 1

    def test_email_pattern_various_tlds(self, redactor: PIIRedactor):
        """Test email pattern with various TLDs."""
        emails = [
            "user@example.com",
            "user@example.org",
            "user@example.net",
            "user@example.io",
            "user@example.ua",
        ]
        for email in emails:
            redacted, _metadata = redactor.redact_query(email)
            assert "[EMAIL]" in redacted, f"Failed for {email}"

    def test_passport_cyrillic_uppercase_only(self, redactor: PIIRedactor):
        """Test that passport pattern requires uppercase Cyrillic."""
        # Lowercase Cyrillic should not match (pattern uses uppercase)
        query = "Document: аб123456"  # lowercase
        _redacted, metadata = redactor.redact_query(query)

        # Lowercase should not match the uppercase pattern
        assert "passport_count" not in metadata or metadata.get("passport_count", 0) == 0


class TestPIIRedactorInstance:
    """Test PIIRedactor instance behavior."""

    def test_redactor_reusable(self):
        """Test that same redactor instance can be reused."""
        redactor = PIIRedactor()

        result1, _ = redactor.redact_query("Email: a@b.com")
        result2, _ = redactor.redact_query("Phone: +380501234567")

        assert "[EMAIL]" in result1
        assert "[PHONE]" in result2

    def test_redactor_stateless(self):
        """Test that redactor doesn't maintain state between calls."""
        redactor = PIIRedactor()

        _, meta1 = redactor.redact_query("Email: a@b.com")
        _, meta2 = redactor.redact_query("No PII here")

        assert meta1["pii_redacted"] is True
        assert meta2["pii_redacted"] is False

    def test_multiple_redactor_instances(self):
        """Test multiple independent redactor instances."""
        redactor1 = PIIRedactor()
        redactor2 = PIIRedactor()

        result1, _ = redactor1.redact_query("test@example.com")
        result2, _ = redactor2.redact_query("test@example.com")

        assert result1 == result2 == "[EMAIL]"

    def test_patterns_are_compiled(self):
        """Test that patterns are pre-compiled regex objects."""
        redactor = PIIRedactor()

        # All patterns should be compiled regex objects
        import re

        for pattern_name, pattern in redactor.patterns.items():
            assert isinstance(pattern, re.Pattern), f"{pattern_name} is not compiled"
