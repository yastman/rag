# tests/unit/test_observability.py
"""Unit tests for PII masking and Langfuse client initialization."""

from datetime import UTC, datetime
from types import SimpleNamespace
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
        """Truncate texts longer than 4000 chars."""
        from telegram_bot.observability import mask_pii

        long_text = "x" * 5000
        result = mask_pii(long_text)
        assert len(result) <= 4015  # 4000 + "... [TRUNCATED]"
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
        with (
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
            patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls,
        ):
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

    def test_initialize_langfuse_runs_model_sync(self):
        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with (
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
            patch("telegram_bot.observability.Langfuse", return_value=fake_client),
            patch(
                "telegram_bot.observability.sync_langfuse_model_definitions", return_value=2
            ) as sync,
        ):
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
                force=True,
            )

        assert result is fake_client
        sync.assert_called_once_with(fake_client)

    def test_initialize_langfuse_ignores_non_string_host_values(self):
        """Non-string host values should be treated as absent and not crash."""
        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with (
            patch("telegram_bot.observability._is_endpoint_reachable") as mock_check,
            patch("telegram_bot.observability.Langfuse", return_value=fake_client),
        ):
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host=MagicMock(),
                force=True,
            )

        assert result is fake_client
        mock_check.assert_not_called()


class TestLangfuseTracingEnvironment:
    """Tests for LANGFUSE_TRACING_ENVIRONMENT support."""

    def test_environment_passed_when_env_var_set(self, monkeypatch):
        """When LANGFUSE_TRACING_ENVIRONMENT is set, it is forwarded to Langfuse(**kwargs)."""
        import telegram_bot.observability as observability

        monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "staging")
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        assert result is fake_client
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("environment") == "staging"

    def test_environment_not_passed_when_env_var_absent(self, monkeypatch):
        """When LANGFUSE_TRACING_ENVIRONMENT is unset, environment key is not in kwargs."""
        import telegram_bot.observability as observability

        monkeypatch.delenv("LANGFUSE_TRACING_ENVIRONMENT", raising=False)
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        assert result is fake_client
        kwargs = mock_cls.call_args.kwargs
        assert "environment" not in kwargs


class TestLangfuseFlushConfig:
    """Tests for LANGFUSE_FLUSH_AT and LANGFUSE_FLUSH_INTERVAL env vars."""

    def test_flush_at_from_env_var(self, monkeypatch):
        """LANGFUSE_FLUSH_AT env var is passed as flush_at to Langfuse SDK."""
        import telegram_bot.observability as observability

        monkeypatch.setenv("LANGFUSE_FLUSH_AT", "25")
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["flush_at"] == 25

    def test_flush_interval_from_env_var(self, monkeypatch):
        """LANGFUSE_FLUSH_INTERVAL env var is passed as flush_interval to Langfuse SDK."""
        import telegram_bot.observability as observability

        monkeypatch.setenv("LANGFUSE_FLUSH_INTERVAL", "10.5")
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["flush_interval"] == 10.5

    def test_flush_at_default_is_sdk_default(self, monkeypatch):
        """When LANGFUSE_FLUSH_AT is not set, flush_at defaults to 512."""
        import telegram_bot.observability as observability

        monkeypatch.delenv("LANGFUSE_FLUSH_AT", raising=False)
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["flush_at"] == 512

    def test_flush_interval_default_is_5_seconds(self, monkeypatch):
        """When LANGFUSE_FLUSH_INTERVAL is not set, flush_interval defaults to 5.0."""
        import telegram_bot.observability as observability

        monkeypatch.delenv("LANGFUSE_FLUSH_INTERVAL", raising=False)
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with patch("telegram_bot.observability.Langfuse", return_value=fake_client) as mock_cls:
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["flush_interval"] == 5.0

    def test_atexit_shutdown_registered_on_init(self, monkeypatch):
        """atexit.register(langfuse.shutdown) is called when Langfuse initializes."""
        import telegram_bot.observability as observability

        monkeypatch.delenv("LANGFUSE_FLUSH_AT", raising=False)
        monkeypatch.delenv("LANGFUSE_FLUSH_INTERVAL", raising=False)
        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with (
            patch("telegram_bot.observability.Langfuse", return_value=fake_client),
            patch("telegram_bot.observability.atexit") as mock_atexit,
        ):
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        mock_atexit.register.assert_called_once_with(fake_client.shutdown)

    def test_atexit_not_registered_when_init_fails(self, monkeypatch):
        """atexit.register is NOT called when Langfuse init fails."""
        import telegram_bot.observability as observability

        monkeypatch.delenv("LANGFUSE_FLUSH_AT", raising=False)
        monkeypatch.delenv("LANGFUSE_FLUSH_INTERVAL", raising=False)
        observability._reset_langfuse_client_for_tests()
        with (
            patch("telegram_bot.observability.Langfuse", side_effect=RuntimeError("boom")),
            patch("telegram_bot.observability.atexit") as mock_atexit,
        ):
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        assert result is None
        mock_atexit.register.assert_not_called()


class TestEndpointReachability:
    """Tests for graceful fallback when Langfuse endpoint is unreachable (#824)."""

    def test_is_endpoint_reachable_returns_false_for_refused_connection(self):
        """_is_endpoint_reachable returns False when connection is refused."""
        from telegram_bot.observability import _is_endpoint_reachable

        # Port 1 is almost never open
        result = _is_endpoint_reachable("http://localhost:1", timeout=0.1)
        assert result is False

    def test_is_endpoint_reachable_returns_true_when_port_is_open(self):
        """_is_endpoint_reachable returns True when host:port accepts connections."""
        import socket

        from telegram_bot.observability import _is_endpoint_reachable

        with socket.socket() as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            result = _is_endpoint_reachable(f"http://127.0.0.1:{port}", timeout=1.0)

        assert result is True

    def test_initialize_langfuse_skips_when_endpoint_unreachable(self):
        """When Langfuse endpoint is unreachable, initialize_langfuse returns None."""
        from unittest.mock import patch

        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        with (
            patch(
                "telegram_bot.observability._is_endpoint_reachable", return_value=False
            ) as mock_check,
            patch("telegram_bot.observability.Langfuse") as mock_langfuse,
        ):
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
                force=True,
            )

        assert result is None
        mock_langfuse.assert_not_called()
        mock_check.assert_called_once()

    def test_initialize_langfuse_proceeds_when_endpoint_reachable(self):
        """When Langfuse endpoint is reachable, initialize_langfuse creates the client."""
        from unittest.mock import MagicMock, patch

        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with (
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
            patch("telegram_bot.observability.Langfuse", return_value=fake_client),
        ):
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
                force=True,
            )

        assert result is fake_client

    def test_initialize_langfuse_logs_warning_once_when_unreachable(self, caplog):
        """When endpoint unreachable, WARNING is logged exactly once (no spam)."""
        import logging
        from unittest.mock import patch

        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        with (
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=False),
            patch("telegram_bot.observability.Langfuse"),
            caplog.at_level(logging.WARNING, logger="telegram_bot.observability"),
        ):
            # First call — should log warning
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
                force=True,
            )
            # Second call without force — should NOT log again (cached None)
            observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

        unreachable_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "unreachable" in r.message.lower()
        ]
        assert len(unreachable_warnings) == 1

    def test_initialize_langfuse_no_endpoint_check_without_host(self):
        """Without explicit host, endpoint check is skipped (cloud default assumed reachable)."""
        from unittest.mock import MagicMock, patch

        import telegram_bot.observability as observability

        observability._reset_langfuse_client_for_tests()
        fake_client = MagicMock()
        with (
            patch("telegram_bot.observability._is_endpoint_reachable") as mock_check,
            patch("telegram_bot.observability.Langfuse", return_value=fake_client),
        ):
            result = observability.initialize_langfuse(
                public_key="pk-test",
                secret_key="sk-test",
                force=True,
            )

        # No host → no reachability check, client created normally
        mock_check.assert_not_called()
        assert result is fake_client


class TestLangfuseModelSync:
    def test_load_model_definitions_from_env_parses_valid_payload(self, monkeypatch):
        import telegram_bot.observability as observability

        monkeypatch.setenv(
            "LANGFUSE_MODEL_DEFINITIONS_JSON",
            """
            [
              {
                "model_name": "zai-glm-4.7",
                "match_pattern": "(?i)^(zai-glm-4\\\\.7)$",
                "unit": "tokens",
                "input_price": "0.000001",
                "output_price": 0.000003,
                "start_date": "2026-02-24T00:00:00Z"
              }
            ]
            """,
        )

        definitions = observability._load_model_definitions_from_env()
        assert len(definitions) == 1
        definition = definitions[0]
        assert definition["model_name"] == "zai-glm-4.7"
        assert definition["match_pattern"] == "(?i)^(zai-glm-4\\.7)$"
        assert definition["unit"] == "TOKENS"
        assert definition["input_price"] == 0.000001
        assert definition["output_price"] == 0.000003
        assert definition["start_date"] == datetime(2026, 2, 24, 0, 0, tzinfo=UTC)

    def test_sync_langfuse_model_definitions_creates_missing_model(self):
        import telegram_bot.observability as observability

        models_api = MagicMock()
        models_api.list.return_value = SimpleNamespace(data=[])
        models_api.create.return_value = SimpleNamespace(
            id="model-1",
            model_name="zai-glm-4.7",
            match_pattern="(?i)^(zai-glm-4\\.7)$",
            is_langfuse_managed=False,
            unit="TOKENS",
            input_price=0.000001,
            output_price=0.000003,
            total_price=None,
            tokenizer_id=None,
        )
        client = MagicMock()
        client.api = SimpleNamespace(models=models_api)

        result = observability.sync_langfuse_model_definitions(
            client,
            definitions=[
                {
                    "model_name": "zai-glm-4.7",
                    "match_pattern": "(?i)^(zai-glm-4\\.7)$",
                    "unit": "TOKENS",
                    "input_price": 0.000001,
                    "output_price": 0.000003,
                }
            ],
        )

        assert result == 1
        models_api.create.assert_called_once()
        req = models_api.create.call_args.kwargs["request"]
        assert req.model_name == "zai-glm-4.7"
        assert req.match_pattern == "(?i)^(zai-glm-4\\.7)$"
        assert req.input_price == 0.000001
        assert req.output_price == 0.000003

    def test_sync_langfuse_model_definitions_updates_stale_custom_model(self):
        import telegram_bot.observability as observability

        stale = SimpleNamespace(
            id="model-old",
            model_name="zai-glm-4.7",
            match_pattern="(?i)^(zai-glm-4\\.7)$",
            is_langfuse_managed=False,
            unit="TOKENS",
            input_price=0.00001,
            output_price=0.00003,
            total_price=None,
            tokenizer_id=None,
        )
        models_api = MagicMock()
        models_api.list.return_value = SimpleNamespace(data=[stale])
        models_api.create.return_value = SimpleNamespace(
            id="model-new",
            model_name="zai-glm-4.7",
            match_pattern="(?i)^(zai-glm-4\\.7)$",
            is_langfuse_managed=False,
            unit="TOKENS",
            input_price=0.000001,
            output_price=0.000003,
            total_price=None,
            tokenizer_id=None,
        )
        client = MagicMock()
        client.api = SimpleNamespace(models=models_api)

        result = observability.sync_langfuse_model_definitions(
            client,
            definitions=[
                {
                    "model_name": "zai-glm-4.7",
                    "match_pattern": "(?i)^(zai-glm-4\\.7)$",
                    "unit": "TOKENS",
                    "input_price": 0.000001,
                    "output_price": 0.000003,
                }
            ],
        )

        assert result == 1
        models_api.delete.assert_called_once_with("model-old")
        models_api.create.assert_called_once()

    def test_sync_langfuse_model_definitions_skips_when_api_missing(self):
        import telegram_bot.observability as observability

        client = MagicMock()
        client.api = None

        result = observability.sync_langfuse_model_definitions(
            client,
            definitions=[
                {
                    "model_name": "x",
                    "match_pattern": "(?i)^x$",
                    "input_price": 1.0,
                    "output_price": 1.0,
                }
            ],
        )

        assert result == 0
