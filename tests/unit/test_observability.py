# tests/unit/test_observability.py
"""Unit tests for PII masking and Langfuse client initialization."""

from unittest.mock import MagicMock, patch


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


class TestLangfuseInitialization:
    def test_initialize_langfuse_returns_none_without_credentials(self, monkeypatch):
        import telegram_bot.observability as observability

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        observability._reset_langfuse_client_for_tests()

        assert observability.initialize_langfuse(force=True) is None

    def test_initialize_langfuse_uses_explicit_config(self):
        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
                force=True,
            )

        assert result is fake_client
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["public_key"] == "pk-test"
        assert kwargs["secret_key"] == "sk-test"
        assert kwargs["host"] == "http://localhost:3001"
        assert callable(kwargs["mask"])

    def test_get_langfuse_client_returns_cached_instance(self):
        import telegram_bot.observability as observability

        fake_client = MagicMock()
        observability._langfuse_client = fake_client
        assert observability.get_langfuse_client() is fake_client
        observability._reset_langfuse_client_for_tests()
