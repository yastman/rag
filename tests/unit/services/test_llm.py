"""Unit tests for LLMService.

Uses AsyncMock for OpenAI SDK client mocking.
"""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.llm import ConfidenceResponse, LLMService


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


class TestLLMServiceInit:
    """Tests for LLMService.__init__."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        service = LLMService(api_key="test-key")

        assert service.api_key == "test-key"
        assert service.base_url == "https://api.openai.com/v1"
        assert service.model == "gpt-4o-mini"
        assert isinstance(service.client, openai.AsyncOpenAI)

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        service = LLMService(
            api_key="custom-key",
            base_url="https://custom.api.com/v1/",
            model="custom-model",
        )

        assert service.api_key == "custom-key"
        assert service.base_url == "https://custom.api.com/v1"  # Trailing slash stripped
        assert service.model == "custom-model"

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base_url."""
        service = LLMService(
            api_key="test-key",
            base_url="https://api.example.com///",
        )

        # rstrip("/") removes ALL trailing slashes
        assert service.base_url == "https://api.example.com"

    def test_init_creates_openai_client(self):
        """Test that AsyncOpenAI client is created."""
        service = LLMService(api_key="test-key")

        assert isinstance(service.client, openai.AsyncOpenAI)


def test_format_context_no_raw_score():
    """_format_context must NOT expose raw RRF scores to LLM."""
    service = LLMService(api_key="test-key")

    chunks = [
        {"text": "ВНЖ по работе", "score": 0.0167, "metadata": {"title": "Виды ВНЖ"}},
        {"text": "ВНЖ пенсионеры", "score": 0.0161, "metadata": {}},
    ]
    result = service._format_context(chunks)
    # Must NOT contain raw RRF scores like "0.02" or "0.017"
    assert "0.02" not in result
    assert "0.017" not in result
    # Must contain object markers
    assert "[Объект 1]" in result
    assert "[Объект 2]" in result


class TestLLMServiceGenerateAnswer:
    """Tests for LLMService.generate_answer."""

    @pytest.fixture
    def sample_chunks(self):
        """Sample context chunks for testing."""
        return [
            {
                "text": "Apartment near beach",
                "metadata": {"title": "Sea View Apt", "city": "Sunny Beach", "price": 50000},
                "score": 0.95,
            },
            {
                "text": "Studio in center",
                "metadata": {"title": "Central Studio", "city": "Sofia", "price": 35000},
                "score": 0.85,
            },
        ]

    async def test_generate_answer_returns_response(self, sample_chunks):
        """Test successful answer generation."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Generated answer text")
        )

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert result == "Generated answer text"

    async def test_configured_max_tokens_used_for_answer_confidence_and_stream(self, sample_chunks):
        """LLM answer paths use the configured generation token budget."""
        service = LLMService(api_key="test-key", max_tokens=1234)

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Generated answer text")
        )
        await service.generate_answer("What apartments?", sample_chunks)
        assert service.client.chat.completions.create.call_args.kwargs["max_tokens"] == 1234

        service._instructor_client = AsyncMock()
        service._instructor_client.chat.completions.create = AsyncMock(
            return_value=ConfidenceResponse(answer="Confident answer", confidence=0.8)
        )
        await service.generate_answer("What apartments?", sample_chunks, with_confidence=True)
        assert (
            service._instructor_client.chat.completions.create.call_args.kwargs["max_tokens"]
            == 1234
        )

        stream_chunk = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="chunk"))])

        async def mock_stream():
            yield stream_chunk

        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())
        chunks = [chunk async for chunk in service.stream_answer("What apartments?", sample_chunks)]
        assert chunks == ["chunk"]
        assert service.client.chat.completions.create.call_args.kwargs["max_tokens"] == 1234

    async def test_generate_answer_custom_system_prompt(self, sample_chunks):
        """Test answer generation with custom system prompt."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Custom response")
        )

        result = await service.generate_answer(
            "Question?", sample_chunks, system_prompt="Custom prompt"
        )

        assert result == "Custom response"
        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["messages"][0]["content"] == "Custom prompt"

    async def test_generate_answer_timeout_fallback(self, sample_chunks):
        """Test fallback on timeout exception."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "Sea View Apt" in result

    async def test_generate_answer_connection_error_fallback(self, sample_chunks):
        """Test fallback on connection error."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )

        result = await service.generate_answer("What apartments?", sample_chunks)

        assert "Сервис генерации ответов временно недоступен" in result

    async def test_generate_answer_empty_chunks_fallback(self):
        """Test fallback with empty chunks."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        result = await service.generate_answer("What apartments?", [])

        assert "Извините, сервис временно недоступен" in result


class TestLLMServiceStreamAnswer:
    """Tests for LLMService.stream_answer."""

    @pytest.fixture
    def sample_chunks(self):
        """Sample context chunks for testing."""
        return [
            {
                "text": "Apartment near beach",
                "metadata": {"title": "Sea View Apt", "city": "Sunny Beach", "price": 50000},
                "score": 0.95,
            },
        ]

    async def test_stream_answer_yields_chunks(self, sample_chunks):
        """Test that stream_answer yields content chunks."""
        service = LLMService(api_key="test-key")

        # Mock streaming response as async iterator
        chunk1 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="Hello"))])
        chunk2 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=" World"))])

        async def mock_stream():
            for c in [chunk1, chunk2]:
                yield c

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    async def test_stream_answer_skips_usage_chunks(self, sample_chunks):
        """Test that usage chunks are skipped."""
        service = LLMService(api_key="test-key")

        content_chunk = MagicMock(
            usage=None, choices=[MagicMock(delta=MagicMock(content="Content"))]
        )
        usage_chunk = MagicMock(usage=MagicMock(total_tokens=100), choices=[])

        async def mock_stream():
            for c in [content_chunk, usage_chunk]:
                yield c

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Content"]

    async def test_stream_answer_timeout_yields_fallback(self, sample_chunks):
        """Test that timeout yields fallback message."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_generic_exception_yields_fallback(self, sample_chunks):
        """Test that generic exception yields fallback message."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("Unknown error"))

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "Сервис генерации ответов временно недоступен" in chunks[0]

    async def test_stream_answer_skips_empty_content(self, sample_chunks):
        """Test that empty content in delta is skipped."""
        service = LLMService(api_key="test-key")

        chunk_empty = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=""))])
        chunk_none = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=None))])
        chunk_actual = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="Actual"))])

        async def mock_stream():
            for c in [chunk_empty, chunk_none, chunk_actual]:
                yield c

        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in service.stream_answer("Question?", sample_chunks):
            chunks.append(chunk)

        assert chunks == ["Actual"]


class TestLLMServiceFormatContext:
    """Tests for LLMService._format_context."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance."""
        return LLMService(api_key="test-key")

    def test_format_context_empty_chunks(self, service):
        """Test formatting with empty chunks list."""
        result = service._format_context([])

        assert result == "Релевантной информации не найдено."

    def test_format_context_single_chunk(self, service):
        """Test formatting with single chunk."""
        chunks = [{"text": "Property description", "score": 0.92}]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "релевантность" not in result
        assert "Property description" in result

    def test_format_context_with_metadata(self, service):
        """Test formatting with full metadata."""
        chunks = [
            {
                "text": "Nice apartment",
                "metadata": {"title": "Beach Apt", "city": "Varna", "price": 75000},
                "score": 0.88,
            }
        ]

        result = service._format_context(chunks)

        assert "Название: Beach Apt" in result
        assert "Город: Varna" in result
        assert "Цена: 75,000" in result
        assert "Nice apartment" in result

    def test_format_context_multiple_chunks(self, service):
        """Test formatting with multiple chunks."""
        chunks = [
            {"text": "First property", "score": 0.95},
            {"text": "Second property", "score": 0.85},
            {"text": "Third property", "score": 0.75},
        ]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "[Объект 2]" in result
        assert "[Объект 3]" in result
        assert "---" in result

    def test_format_context_partial_metadata(self, service):
        """Test formatting with partial metadata (only title)."""
        chunks = [
            {
                "text": "Property text",
                "metadata": {"title": "Only Title"},
                "score": 0.80,
            }
        ]

        result = service._format_context(chunks)

        assert "Название: Only Title" in result
        assert "Город:" not in result
        assert "Цена:" not in result

    def test_format_context_no_metadata(self, service):
        """Test formatting without metadata dict."""
        chunks = [{"text": "Just text", "score": 0.70}]

        result = service._format_context(chunks)

        assert "Just text" in result
        assert "Название:" not in result

    def test_format_context_missing_score(self, service):
        """Test formatting when score is missing (defaults to 0)."""
        chunks = [{"text": "No score", "metadata": {}}]

        result = service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "релевантность" not in result


class TestLLMServiceGetFallbackAnswer:
    """Tests for LLMService._get_fallback_answer."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance."""
        return LLMService(api_key="test-key")

    def test_get_fallback_answer_empty_chunks(self, service):
        """Test fallback with empty chunks."""
        result = service._get_fallback_answer("Question?", [])

        assert "Извините, сервис временно недоступен" in result
        assert "Попробуйте повторить запрос позже" in result

    def test_get_fallback_answer_formats_first_3_chunks(self, service):
        """Test that only first 3 chunks are formatted."""
        chunks = [
            {"text": "1", "metadata": {"title": "First"}},
            {"text": "2", "metadata": {"title": "Second"}},
            {"text": "3", "metadata": {"title": "Third"}},
            {"text": "4", "metadata": {"title": "Fourth"}},
            {"text": "5", "metadata": {"title": "Fifth"}},
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "1. First" in result
        assert "2. Second" in result
        assert "3. Third" in result
        assert "Fourth" not in result
        assert "Fifth" not in result

    def test_get_fallback_answer_handles_non_numeric_price(self, service):
        """Test fallback handles non-numeric price values."""
        chunks = [
            {
                "text": "Property",
                "metadata": {"title": "Test", "price": "negotiable"},
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Цена: negotiable" in result

    def test_get_fallback_answer_numeric_price(self, service):
        """Test fallback formats numeric price with separator."""
        chunks = [
            {
                "text": "Property",
                "metadata": {"title": "Test", "price": 125000},
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Цена: 125,000" in result

    def test_get_fallback_answer_all_metadata_fields(self, service):
        """Test fallback includes all metadata fields."""
        chunks = [
            {
                "text": "Description",
                "metadata": {
                    "title": "Luxury Apt",
                    "price": 200000,
                    "city": "Burgas",
                    "rooms": 3,
                },
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Luxury Apt" in result
        assert "Цена: 200,000" in result
        assert "Город: Burgas" in result
        assert "Комнат: 3" in result

    def test_get_fallback_answer_partial_metadata(self, service):
        """Test fallback with partial metadata."""
        chunks = [
            {
                "text": "Description",
                "metadata": {"city": "Sofia"},
            }
        ]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Город: Sofia" in result
        assert "1. " in result

    def test_get_fallback_answer_no_metadata(self, service):
        """Test fallback with chunk having no metadata."""
        chunks = [{"text": "Just description"}]

        result = service._get_fallback_answer("Question?", chunks)

        assert "Сервис генерации ответов временно недоступен" in result
        assert "1. " in result


class TestLLMServiceGenerate:
    """Tests for LLMService.generate method."""

    async def test_generate_returns_content(self):
        """Test successful generation."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Generated text")
        )

        result = await service.generate("Test prompt")

        assert result == "Generated text"

    async def test_generate_uses_low_temperature(self):
        """Test that generate uses low temperature for deterministic output."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("Prompt")

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0.3

    async def test_generate_custom_max_tokens(self):
        """Test generate with custom max_tokens."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("Prompt", max_tokens=500)

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == 500

    async def test_generate_default_max_tokens(self):
        """Test generate uses default max_tokens of 200."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("Prompt")

        call_args = service.client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == 200

    async def test_generate_raises_on_error(self):
        """Test that generate raises exception on API error."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with pytest.raises(Exception, match="API error"):
            await service.generate("Prompt")

    async def test_generate_sends_correct_message_format(self):
        """Test that generate sends simple user message format."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Response")
        )

        await service.generate("My prompt")

        call_args = service.client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "My prompt"


class TestLLMServiceClose:
    """Tests for LLMService.close method."""

    async def test_close_calls_close(self):
        """Test that close method calls close on the client."""
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()

        await service.close()

        service.client.close.assert_called_once()

    async def test_close_integration(self):
        """Test close with real client (integration-style)."""
        service = LLMService(api_key="test-key")

        # Should not raise
        await service.close()


class TestLLMServiceObserveInstrumentation:
    """Tests for @observe instrumentation on LLMService public methods (#1660).

    Contract: ``generate_answer`` (line ~97), ``stream_answer`` (line ~213) and
    ``generate`` (line ~366) must each be wrapped with::

        @observe(name="llm-service-<method>",
                 capture_input=False, capture_output=False)

    so the auto-traced generation produced by ``langfuse.openai.AsyncOpenAI``
    becomes a child of a named span instead of an orphan top-level trace.

    CRITICAL (audit correction on #1660): the wrapper must NOT use
    ``as_type="generation"``. ``langfuse.openai`` already creates a generation
    observation for each ``chat.completions.create()`` call — making the
    wrapper itself a generation would produce duplicate generation
    observations for one LLM call. Plain span > nested generation is the
    intended structure.

    Curated ``update_current_span`` payloads avoid leaking full prompt/full
    response into Langfuse. On LLM exception the span is recorded at
    ``level="ERROR"`` with a truncated ``status_message``; ``generate``
    re-raises while ``generate_answer``/``stream_answer`` already swallow API
    errors and yield/return a fallback (existing public contract preserved).
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Replace get_client used by the llm module with a recording mock."""
        from telegram_bot.services import llm as llm_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(llm_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe(monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the @observe decorator at module-import time with a no-op.

        Uses ``monkeypatch.delitem(sys.modules, ...)`` so that after the test
        the ORIGINAL module object is restored — otherwise the reload would
        leave a fresh ``LLMService`` class in ``sys.modules`` and downstream
        tests that assert ``services.LLMService is LLMService`` (identity)
        would fail due to drift between the lazy-imported package attribute
        and the test-file-level binding.
        """
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        monkeypatch.delitem(sys.modules, "telegram_bot.services.llm", raising=False)
        importlib.import_module("telegram_bot.services.llm")

    @staticmethod
    def _record_observe_calls(
        monkeypatch: pytest.MonkeyPatch,
    ) -> list[dict[str, object]]:
        """Replace @observe with a recorder and reload the llm module.

        Same ``monkeypatch.delitem`` strategy as ``_disable_observe`` — the
        original module is restored on test teardown.
        """
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        captured_calls: list[dict[str, object]] = []

        def recording_observe(**kwargs):
            captured_calls.append(kwargs)

            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", recording_observe)
        monkeypatch.delitem(sys.modules, "telegram_bot.services.llm", raising=False)
        importlib.import_module("telegram_bot.services.llm")
        return captured_calls

    # ------------------------------------------------------------------
    # Module-level wiring
    # ------------------------------------------------------------------

    def test_module_imports_observe_and_get_client(self):
        """Module wires the Langfuse decorator + client accessor (#1660 contract)."""
        from telegram_bot.services import llm as llm_mod

        assert hasattr(llm_mod, "observe"), (
            "telegram_bot.services.llm must import `observe` from "
            "telegram_bot.observability for the @observe decorator on "
            "LLMService.{generate_answer,stream_answer,generate}"
        )
        assert hasattr(llm_mod, "get_client"), (
            "telegram_bot.services.llm must import `get_client` from "
            "telegram_bot.observability for curated update_current_span calls"
        )

    # ------------------------------------------------------------------
    # Decorator kwargs (one test per method)
    # ------------------------------------------------------------------

    def test_generate_answer_decorator_kwargs(self, monkeypatch):
        """``generate_answer`` is decorated with the audit's exact kwargs.

        CRITICAL: ``as_type="generation"`` MUST NOT be present (audit
        correction on #1660). The class uses ``langfuse.openai.AsyncOpenAI``
        which already creates a generation for each call — the wrapper is a
        plain span, langfuse.openai owns the nested generation.
        """
        captured = self._record_observe_calls(monkeypatch)

        matches = [c for c in captured if c.get("name") == "llm-service-generate-answer"]
        assert len(matches) == 1, (
            "Expected exactly one @observe(name='llm-service-generate-answer', ...) "
            f"on LLMService.generate_answer; observed names: {[c.get('name') for c in captured]}"
        )
        kwargs = matches[0]
        assert kwargs.get("capture_input") is False
        assert kwargs.get("capture_output") is False
        assert "as_type" not in kwargs, (
            "Wrapper must NOT use as_type='generation' (audit correction on #1660): "
            "langfuse.openai already creates a generation for each chat.completions.create; "
            "wrapping the public method as another generation would produce duplicates."
        )

    def test_stream_answer_decorator_kwargs(self, monkeypatch):
        """``stream_answer`` is a plain span — NO as_type=generation (audit)."""
        captured = self._record_observe_calls(monkeypatch)

        matches = [c for c in captured if c.get("name") == "llm-service-stream-answer"]
        assert len(matches) == 1, (
            "Expected exactly one @observe(name='llm-service-stream-answer', ...) "
            f"on LLMService.stream_answer; observed names: {[c.get('name') for c in captured]}"
        )
        kwargs = matches[0]
        assert kwargs.get("capture_input") is False
        assert kwargs.get("capture_output") is False
        assert "as_type" not in kwargs, (
            "stream_answer wrapper must NOT use as_type='generation' (audit "
            "correction on #1660): langfuse.openai handles the streaming "
            "generation; wrapper stays a plain span."
        )

    def test_generate_decorator_kwargs(self, monkeypatch):
        """``generate`` is decorated as a plain span — NO as_type=generation."""
        captured = self._record_observe_calls(monkeypatch)

        matches = [c for c in captured if c.get("name") == "llm-service-generate"]
        assert len(matches) == 1, (
            "Expected exactly one @observe(name='llm-service-generate', ...) "
            f"on LLMService.generate; observed names: {[c.get('name') for c in captured]}"
        )
        kwargs = matches[0]
        assert kwargs.get("capture_input") is False
        assert kwargs.get("capture_output") is False
        assert "as_type" not in kwargs, (
            "generate wrapper must NOT use as_type='generation' (audit correction on #1660)."
        )

    # ------------------------------------------------------------------
    # Behavior: generate_answer
    # ------------------------------------------------------------------

    async def test_generate_answer_curated_input_no_full_prompt(self, monkeypatch):
        """``generate_answer`` records prompt_preview/model/with_confidence only.

        Full prompt MUST NOT appear in span input (#1660 Forbidden section).
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key", model="gpt-4o-mini")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("ok"))

        long_question = (
            "Это очень длинный вопрос про недвижимость в Болгарии, "
            "который точно длиннее ста двадцати символов и должен быть "
            "усечён в превью при записи в Langfuse span input."
        )
        assert len(long_question) > 120

        await service.generate_answer(long_question, [{"text": "ctx"}])

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "input" in c.kwargs
        ]
        assert input_calls, "update_current_span(input=...) was never called on generate_answer"
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert "prompt_preview" in captured_input
        assert isinstance(captured_input["prompt_preview"], str)
        assert len(captured_input["prompt_preview"]) <= 120
        assert captured_input.get("model") == "gpt-4o-mini"
        assert "with_confidence" in captured_input
        assert captured_input["with_confidence"] is False

        # Forbidden: full question MUST NOT appear in span input.
        assert long_question not in str(captured_input)

    async def test_generate_answer_curated_output_response_len(self, monkeypatch):
        """``generate_answer`` records response_len after LLM (#1660 plan)."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        long_response = (
            "Подобрал три варианта 2BR у моря в Несебре от 65к EUR. "
            "Все с видом на море и инфраструктурой в шаговой доступности."
        )
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(long_response)
        )

        result = await service.generate_answer("вопрос", [{"text": "ctx"}])
        assert result == long_response  # behavior unchanged

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert output_calls, "update_current_span(output=...) was never called on generate_answer"
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert captured_output.get("response_len") == len(long_response)
        # Forbidden: full response text MUST NOT appear in span output.
        assert long_response not in str(captured_output)

    async def test_generate_answer_error_path_records_error_level(self, monkeypatch):
        """Per audit: on internal failure, span level=ERROR with truncated msg.

        ``generate_answer`` already swallows OpenAI errors and returns a
        fallback string, so the public method does NOT re-raise. The error
        path must still be recorded on the span (#1660 plan step 4).
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM exploded mid-generate-answer")
        )

        result = await service.generate_answer(
            "q",
            [{"text": "ctx", "metadata": {"title": "X"}}],
        )
        assert isinstance(result, str)
        assert "Сервис генерации ответов временно недоступен" in result

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, (
            "Failure path must call update_current_span(level='ERROR', ...) "
            "on LLMService.generate_answer (#1660 plan step 4)"
        )
        status = error_calls[0].get("status_message", "")
        assert "LLM exploded mid-generate-answer" in status
        assert len(status) <= 220

    # ------------------------------------------------------------------
    # Behavior: stream_answer
    # ------------------------------------------------------------------

    async def test_stream_answer_curated_input_no_full_prompt(self, monkeypatch):
        """``stream_answer`` records prompt_preview/model only — no full prompt."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        long_question = (
            "Это очень-очень-очень длинный вопрос на стрим, который "
            "превышает сто двадцать символов и должен быть аккуратно "
            "усечён до prompt_preview ровно в 120 символов или меньше."
        )
        assert len(long_question) > 120

        chunk1 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="A"))])
        chunk2 = MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content="B"))])

        async def stream():
            for c in [chunk1, chunk2]:
                yield c

        service = LLMService(api_key="test-key", model="gpt-4o-mini")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=stream())

        chunks = [c async for c in service.stream_answer(long_question, [{"text": "ctx"}])]
        assert chunks == ["A", "B"]

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "input" in c.kwargs
        ]
        assert input_calls, "update_current_span(input=...) was never called on stream_answer"
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert "prompt_preview" in captured_input
        assert isinstance(captured_input["prompt_preview"], str)
        assert len(captured_input["prompt_preview"]) <= 120
        assert captured_input.get("model") == "gpt-4o-mini"
        # Forbidden: full question MUST NOT appear in span input.
        assert long_question not in str(captured_input)

    async def test_stream_answer_curated_output_chunks_and_total_len(self, monkeypatch):
        """``stream_answer`` records {chunks, total_len} after generator drains."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        contents = ["Hel", "lo ", "World!"]
        body_chunks = [
            MagicMock(usage=None, choices=[MagicMock(delta=MagicMock(content=c))]) for c in contents
        ]
        usage_tail = MagicMock(usage=MagicMock(total_tokens=42), choices=[])

        async def stream():
            for c in [*body_chunks, usage_tail]:
                yield c

        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=stream())

        full = ""
        async for c in service.stream_answer("q", [{"text": "ctx"}]):
            full += c
        assert full == "Hello World!"

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert output_calls, (
            "update_current_span(output=...) was never called on stream_answer "
            "after the generator finished"
        )
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert captured_output.get("chunks") == 3, (
            f"Expected chunks=3 (body chunks only, usage chunk skipped), "
            f"got {captured_output.get('chunks')}"
        )
        assert captured_output.get("total_len") == len(full)

        # Forbidden: full response text MUST NOT appear in span output.
        assert full not in str(captured_output)

    async def test_stream_answer_error_path_records_error_level(self, monkeypatch):
        """On stream failure, span level=ERROR + status_message; fallback yields."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM exploded mid-stream-answer")
        )

        chunks = [
            c
            async for c in service.stream_answer("q", [{"text": "ctx", "metadata": {"title": "X"}}])
        ]
        assert chunks, "stream_answer must still yield a fallback chunk on error"

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, (
            "Failure path must call update_current_span(level='ERROR', ...) "
            "on LLMService.stream_answer (#1660 plan step 4)"
        )
        status = error_calls[0].get("status_message", "")
        assert "LLM exploded mid-stream-answer" in status
        assert len(status) <= 220

    async def test_stream_options_include_usage_preserved(self, monkeypatch):
        """Sanity guard: ``stream_options={"include_usage": True}`` not regressed.

        The audit on #1660 explicitly notes the existing call already passes
        ``stream_options={"include_usage": True}`` (line ~245-252 of llm.py
        on dev) and that it MUST be preserved so langfuse.openai can read
        token usage from the final chunk and attach it to the nested
        generation observation.
        """
        self._disable_observe(monkeypatch)
        self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        async def empty_stream():
            return
            yield  # pragma: no cover

        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=empty_stream())

        async for _ in service.stream_answer("q", [{"text": "ctx"}]):
            pass

        kwargs = service.client.chat.completions.create.call_args.kwargs
        assert kwargs.get("stream") is True
        assert kwargs.get("stream_options") == {"include_usage": True}, (
            "stream_options={'include_usage': True} must be preserved "
            "(audit on #1660: required for langfuse.openai to capture token "
            "usage from the final streaming chunk)"
        )

    # ------------------------------------------------------------------
    # Behavior: generate
    # ------------------------------------------------------------------

    async def test_generate_curated_input_no_full_prompt(self, monkeypatch):
        """``generate`` records prompt_preview/model only — no full prompt."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        long_prompt = (
            "Очень длинный системный промт для CESC, который содержит "
            "более ста двадцати символов и должен попасть в span только "
            "в виде prompt_preview, никогда полностью."
        )
        assert len(long_prompt) > 120

        service = LLMService(api_key="test-key", model="gpt-4o-mini")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("ok"))

        await service.generate(long_prompt)

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "input" in c.kwargs
        ]
        assert input_calls, "update_current_span(input=...) was never called on generate"
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert "prompt_preview" in captured_input
        assert isinstance(captured_input["prompt_preview"], str)
        assert len(captured_input["prompt_preview"]) <= 120
        assert captured_input.get("model") == "gpt-4o-mini"
        # Forbidden: full prompt MUST NOT appear in span input.
        assert long_prompt not in str(captured_input)

    async def test_generate_curated_output_response_len(self, monkeypatch):
        """``generate`` records response_len after LLM (#1660 plan)."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        long_response = "Сгенерированный длинный ответ для CESC извлечения предпочтений клиента."
        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(long_response)
        )

        result = await service.generate("prompt")
        assert result == long_response  # behavior unchanged

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert output_calls, "update_current_span(output=...) was never called on generate"
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert captured_output.get("response_len") == len(long_response)
        # Forbidden: full response text MUST NOT appear in span output.
        assert long_response not in str(captured_output)

    async def test_generate_error_path_records_error_level_and_reraises(self, monkeypatch):
        """``generate`` records ERROR span and RE-RAISES (existing contract).

        Unlike ``generate_answer``/``stream_answer`` which swallow API errors
        and emit a fallback string, ``generate`` re-raises (verified by the
        existing ``test_generate_raises_on_error`` test in this file). The
        @observe wrapper must record the error span before the exception
        propagates.
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.llm import LLMService

        service = LLMService(api_key="test-key")
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM exploded mid-generate")
        )

        with pytest.raises(RuntimeError, match="LLM exploded mid-generate"):
            await service.generate("prompt")

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, (
            "Failure path must call update_current_span(level='ERROR', ...) "
            "on LLMService.generate (#1660 plan step 4)"
        )
        status = error_calls[0].get("status_message", "")
        assert "LLM exploded mid-generate" in status
        assert len(status) <= 220
