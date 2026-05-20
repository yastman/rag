"""Tests for HyDE (Hypothetical Document Embeddings) functionality (OpenAI SDK)."""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.query_preprocessor import HyDEGenerator, QueryPreprocessor


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


class TestQueryPreprocessorHyDE:
    """Tests for HyDE-related methods in QueryPreprocessor."""

    def test_count_words_simple(self):
        pp = QueryPreprocessor()
        assert pp.count_words("квартира у моря") == 3

    def test_count_words_single_word(self):
        pp = QueryPreprocessor()
        assert pp.count_words("студия") == 1

    def test_count_words_long_query(self):
        pp = QueryPreprocessor()
        assert pp.count_words("двухкомнатная квартира с видом на море недалеко от центра") == 9

    def test_should_use_hyde_short_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("квартира море") is True

    def test_should_use_hyde_long_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("двухкомнатная квартира в центре Несебра дешево") is False

    def test_should_use_hyde_exact_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("ID 12345") is False

    def test_should_use_hyde_corpus_query(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("корпус 5") is False

    def test_should_use_hyde_custom_threshold(self):
        pp = QueryPreprocessor()
        assert pp.should_use_hyde("квартира у моря", min_words=4) is True
        assert pp.should_use_hyde("квартира у моря", min_words=3) is False

    def test_analyze_includes_hyde_fields(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия")
        assert "use_hyde" in result
        assert "word_count" in result

    def test_analyze_hyde_disabled_by_default(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=False)
        assert result["use_hyde"] is False

    def test_analyze_hyde_enabled_for_short_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is True
        assert result["word_count"] == 1

    def test_analyze_hyde_disabled_for_long_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze(
            "двухкомнатная квартира с видом на море недорого",
            use_hyde=True,
            hyde_min_words=5,
        )
        assert result["use_hyde"] is False
        assert result["word_count"] == 7

    def test_analyze_hyde_disabled_for_exact_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("корпус 5", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is False
        assert result["is_exact"] is True


class TestHyDEGenerator:
    """Tests for HyDEGenerator class (OpenAI SDK)."""

    def test_init_defaults(self):
        hyde = HyDEGenerator()
        assert hyde.api_key == "not-needed"
        assert hyde.base_url == "http://localhost:4000"
        assert hyde.model == "gpt-4o-mini"

    def test_init_custom_params(self):
        hyde = HyDEGenerator(
            api_key="test-key",
            base_url="http://custom:5000/",
            model="gpt-4o",
        )
        assert hyde.api_key == "test-key"
        assert hyde.base_url == "http://custom:5000"
        assert hyde.model == "gpt-4o"

    def test_init_creates_openai_client(self):
        from openai import AsyncOpenAI

        hyde = HyDEGenerator()
        assert isinstance(hyde.client, AsyncOpenAI)

    async def test_generate_hypothetical_document_success(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Уютная квартира в Несебре, 45м², рядом с пляжем.")
        )

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert "Несебре" in result or "квартира" in result.lower()
        hyde.client.chat.completions.create.assert_called_once()

    async def test_generate_hypothetical_document_fallback_on_error(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert result == "квартира у моря"

    async def test_generate_hypothetical_document_fallback_on_generic_error(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(side_effect=Exception("Connection failed"))

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert result == "квартира у моря"

    async def test_generate_hypothetical_document_api_call_structure(self):
        hyde = HyDEGenerator(
            api_key="test-key",
            base_url="http://test:4000",
            model="test-model",
        )
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Test response")
        )

        await hyde.generate_hypothetical_document("test query")

        call_kwargs = hyde.client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 200
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"
        assert "test query" in call_kwargs["messages"][1]["content"]

    async def test_close(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()

        await hyde.close()

        hyde.client.close.assert_called_once()

    async def test_generate_handles_none_content(self):
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(return_value=_mock_completion(None))

        result = await hyde.generate_hypothetical_document("квартира")

        # Should fallback to query when content is None
        assert result == "квартира"


class TestHyDEObserveInstrumentation:
    """Tests for @observe instrumentation on HyDEGenerator (#1661).

    Contract: generate_hypothetical_document must be wrapped with @observe so
    nested generation observations created by langfuse.openai are parented
    under a named span instead of becoming orphan traces. Curated input/output
    payloads are written via update_current_span; full prompts and full
    documents must NOT appear in span fields.
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Replace get_client used by HyDE module with a recording mock."""
        from telegram_bot.services import query_preprocessor as qp_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(qp_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe(monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the @observe decorator at module-import time with a no-op.

        This lets behavior assertions (input/output/error) run without the real
        Langfuse SDK trying to start an OTEL span.
        """
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        # Reload query_preprocessor so it picks up the no-op decorator.
        sys.modules.pop("telegram_bot.services.query_preprocessor", None)
        importlib.import_module("telegram_bot.services.query_preprocessor")

    def test_module_imports_observe_and_get_client(self):
        """Module wires the Langfuse decorator + client accessor (#1661 contract)."""
        from telegram_bot.services import query_preprocessor as qp_mod

        assert hasattr(qp_mod, "observe"), (
            "telegram_bot.services.query_preprocessor must import `observe` "
            "from telegram_bot.observability for the @observe decorator on "
            "HyDEGenerator.generate_hypothetical_document"
        )
        assert hasattr(qp_mod, "get_client"), (
            "telegram_bot.services.query_preprocessor must import `get_client` "
            "from telegram_bot.observability for curated update_current_span calls"
        )

    def test_observe_decorator_applied_with_correct_kwargs(self, monkeypatch):
        """@observe must be applied with the trace-coverage audit's exact kwargs."""
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        captured: dict[str, object] = {}

        def recording_observe(**kwargs):
            captured.update(kwargs)

            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", recording_observe)
        sys.modules.pop("telegram_bot.services.query_preprocessor", None)
        importlib.import_module("telegram_bot.services.query_preprocessor")

        assert captured.get("name") == "hyde-generate-document"
        assert captured.get("capture_input") is False
        assert captured.get("capture_output") is False

    async def test_input_payload_is_curated_preview_only(self, monkeypatch):
        """Span input must be a curated dict (no full query, no full prompt)."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        # Re-import to bind the no-op observe applied above.
        from telegram_bot.services.query_preprocessor import HyDEGenerator

        hyde = HyDEGenerator(model="test-model")
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(return_value=_mock_completion("ok"))

        long_query = "квартира у моря " * 20  # > 120 chars

        await hyde.generate_hypothetical_document(long_query)

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "input" in c.kwargs
        ]
        assert len(input_calls) >= 1, "update_current_span(input=...) was never called"
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert captured_input.get("model") == "test-model"
        preview = captured_input.get("query_preview", "")
        assert len(preview) <= 120
        assert long_query not in str(captured_input), "Full query must not appear in span input"
        assert HyDEGenerator.HYDE_SYSTEM_PROMPT not in str(captured_input), (
            "System prompt must not be captured in span input"
        )

    async def test_output_payload_is_curated_preview_only(self, monkeypatch):
        """Span output must record preview + token-estimate, not full document."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.query_preprocessor import HyDEGenerator

        long_doc = "Подробное описание объекта недвижимости. " * 30
        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(return_value=_mock_completion(long_doc))

        await hyde.generate_hypothetical_document("квартира у моря")

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert len(output_calls) >= 1, "update_current_span(output=...) was never called"
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        preview = captured_output.get("document_preview", "")
        assert len(preview) <= 200
        assert "tokens_estimated" in captured_output
        assert isinstance(captured_output["tokens_estimated"], int)
        assert long_doc not in str(captured_output), (
            "Full generated document must not appear in span output"
        )

    async def test_generate_works_when_langfuse_client_unavailable(self, monkeypatch):
        """HyDE generation must not require an initialized Langfuse client."""
        self._disable_observe(monkeypatch)

        from telegram_bot.services import query_preprocessor as qp_mod
        from telegram_bot.services.query_preprocessor import HyDEGenerator

        monkeypatch.setattr(qp_mod, "get_client", lambda: None)

        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Уютная квартира рядом с морем.")
        )

        result = await hyde.generate_hypothetical_document("квартира у моря")

        assert result == "Уютная квартира рядом с морем."

    async def test_exception_path_records_error_level(self, monkeypatch):
        """On exception, update_current_span must be called with level='ERROR'."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.query_preprocessor import HyDEGenerator

        hyde = HyDEGenerator()
        hyde.client = AsyncMock()
        hyde.client.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM exploded"))

        result = await hyde.generate_hypothetical_document("квартира у моря")

        # Fallback semantics preserved (issue forbids changing fallback path).
        assert result == "квартира у моря"

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert len(error_calls) >= 1, (
            "Failure path must call update_current_span(level='ERROR', ...)"
        )
        status = error_calls[0].get("status_message", "")
        assert "LLM exploded" in status
        assert len(status) <= 220, "status_message must be truncated to ~200 chars"


class TestHyDEIntegration:
    """Integration tests for HyDE with QueryPreprocessor."""

    def test_hyde_workflow_short_semantic_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("квартира море", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is True
        assert result["word_count"] == 2
        assert result["is_exact"] is False

    def test_hyde_workflow_short_exact_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze("ID 12345", use_hyde=True, hyde_min_words=5)
        assert result["use_hyde"] is False
        assert result["is_exact"] is True

    def test_hyde_workflow_long_query(self):
        pp = QueryPreprocessor()
        result = pp.analyze(
            "ищу двухкомнатную квартиру в Несебре рядом с морем",
            use_hyde=True,
            hyde_min_words=5,
        )
        assert result["use_hyde"] is False
        assert result["word_count"] == 8

    def test_hyde_disabled_globally(self):
        pp = QueryPreprocessor()
        result = pp.analyze("студия", use_hyde=False, hyde_min_words=5)
        assert result["use_hyde"] is False

    def test_analyze_backward_compatible(self):
        pp = QueryPreprocessor()
        result = pp.analyze("квартира в Бургасе")
        assert "original_query" in result
        assert "normalized_query" in result
        assert result["use_hyde"] is False


class TestHyDESystemPrompt:
    """Tests for HyDE system prompt configuration."""

    def test_system_prompt_in_russian(self):
        assert "Ты" in HyDEGenerator.HYDE_SYSTEM_PROMPT
        assert "недвижимости" in HyDEGenerator.HYDE_SYSTEM_PROMPT

    def test_system_prompt_has_rules(self):
        assert "ПРАВИЛА" in HyDEGenerator.HYDE_SYSTEM_PROMPT

    def test_system_prompt_has_example(self):
        assert "Пример" in HyDEGenerator.HYDE_SYSTEM_PROMPT
        assert "квартира у моря" in HyDEGenerator.HYDE_SYSTEM_PROMPT
