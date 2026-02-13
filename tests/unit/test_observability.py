# tests/unit/test_observability.py
"""Unit tests for PII masking and Langfuse client initialization."""


class TestMaskPii:
    """Tests for mask_pii function."""

    def test_mask_user_id_in_string(self):
        """Mask 9-10 digit user IDs in strings."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("User 123456789 sent a message")
        assert "123456789" not in result
        assert "[USER_ID]" in result

    def test_mask_phone_number(self):
        """Mask phone numbers in international format."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("Call me at +79161234567")
        assert "+79161234567" not in result
        assert "[PHONE]" in result

    def test_mask_email(self):
        """Mask email addresses."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("Contact test@example.com for info")
        assert "test@example.com" not in result
        assert "[EMAIL]" in result

    def test_truncate_long_text(self):
        """Truncate texts longer than 500 chars."""
        from telegram_bot.observability import mask_pii

        long_text = "x" * 1000
        result = mask_pii(long_text)
        assert len(result) <= 520  # 500 + "... [TRUNCATED]"
        assert "[TRUNCATED]" in result

    def test_mask_dict_recursively(self):
        """Mask PII in nested dicts."""
        from telegram_bot.observability import mask_pii

        data = {"user_id": "123456789", "nested": {"email": "test@example.com"}}
        result = mask_pii(data)
        assert result["user_id"] == "[USER_ID]"
        assert result["nested"]["email"] == "[EMAIL]"

    def test_mask_list_items(self):
        """Mask PII in list items."""
        from telegram_bot.observability import mask_pii

        data = ["User 123456789", "Call +79161234567"]
        result = mask_pii(data)
        assert "[USER_ID]" in result[0]
        assert "[PHONE]" in result[1]

    def test_preserve_non_pii_data(self):
        """Non-PII data should remain unchanged."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("квартира 3 комнаты 50000 евро")
        assert result == "квартира 3 комнаты 50000 евро"


class TestTracedPipeline:
    """Tests for traced_pipeline context manager."""

    def test_traced_pipeline_is_context_manager(self):
        from telegram_bot.observability import traced_pipeline

        with traced_pipeline(session_id="test-123", user_id="user-1"):
            pass  # should not raise

    def test_traced_pipeline_accepts_tags(self):
        from telegram_bot.observability import traced_pipeline

        with traced_pipeline(session_id="s", user_id="u", tags=["a", "b"]):
            pass


class TestNullLangfuseClient:
    def test_create_score_is_noop(self):
        from telegram_bot.observability import _NullLangfuseClient

        client = _NullLangfuseClient()
        client.create_score(trace_id="abc123", name="user_feedback", value=1.0, data_type="NUMERIC")

    def test_get_current_trace_id_returns_empty(self):
        from telegram_bot.observability import _NullLangfuseClient

        client = _NullLangfuseClient()
        result = client.get_current_trace_id()
        assert result == ""
