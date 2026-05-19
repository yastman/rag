"""Unit tests for QueryAnalyzer service (Instructor SDK)."""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.query_analyzer import QueryAnalysisResult, QueryAnalyzer


pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


# =============================================================================
# TestQueryAnalyzerInit
# =============================================================================


class TestQueryAnalyzerInit:
    """Tests for QueryAnalyzer initialization."""

    def test_init_stores_api_key(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert analyzer.api_key == "test-api-key"

    def test_init_stores_base_url(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert analyzer.base_url == "http://localhost:8000"

    def test_init_strips_trailing_slash(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000/")
        assert analyzer.base_url == "http://localhost:8000"

    def test_init_default_model(self):
        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert analyzer.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o"
        )
        assert analyzer.model == "gpt-4o"

    def test_init_creates_openai_client(self):
        from openai import AsyncOpenAI

        analyzer = QueryAnalyzer(api_key="test-api-key", base_url="http://localhost:8000")
        assert isinstance(analyzer.client, AsyncOpenAI)

    def test_init_with_different_models(self):
        test_models = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "glm-4"]
        for model in test_models:
            analyzer = QueryAnalyzer(
                api_key="test-key", base_url="http://localhost:8000", model=model
            )
            assert analyzer.model == model, f"Failed for model: {model}"


# =============================================================================
# TestQueryAnalyzerAnalyze
# =============================================================================


class TestQueryAnalyzerAnalyze:
    """Tests for QueryAnalyzer.analyze method."""

    @pytest.fixture
    def analyzer(self):
        """Create QueryAnalyzer with mocked Instructor client."""
        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer._instructor_client = AsyncMock()
        return analyzer

    async def test_analyze_returns_filters_and_semantic_query(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={"price": {"lt": 100000}, "city": "Несебр"},
                semantic_query="уютная квартира с хорошим ремонтом",
            )
        )

        result = await analyzer.analyze("квартира до 100000 евро в Несебре с хорошим ремонтом")

        assert "filters" in result
        assert "semantic_query" in result
        assert result["filters"] == {"price": {"lt": 100000}, "city": "Несебр"}
        assert result["semantic_query"] == "уютная квартира с хорошим ремонтом"

    async def test_analyze_calls_instructor_sdk(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test query")
        )

        await analyzer.analyze("test query")

        analyzer._instructor_client.chat.completions.create.assert_called_once()

    async def test_analyze_uses_instructor_response_model(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_model"] is QueryAnalysisResult
        assert call_kwargs["max_retries"] == 2

    async def test_analyze_uses_zero_temperature(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.0

    async def test_analyze_sends_query_in_user_message(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        test_query = "квартира в Солнечном берегу до 50000 евро"
        await analyzer.analyze(test_query)

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert test_query in user_message["content"]

    async def test_analyze_uses_specified_model(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    async def test_analyze_fallback_on_instructor_error(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Instructor validation failed")
        )

        original_query = "квартира в Бургасе"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_api_connection_error(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )

        original_query = "студия на первой линии"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_rate_limit_error(self, analyzer):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="Rate limited",
                response=mock_resp,
                body=None,
            )
        )

        original_query = "квартира с видом на море"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_fallback_on_timeout_error(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        original_query = "квартира с видом на море"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {}
        assert result["semantic_query"] == original_query

    async def test_analyze_returns_empty_filters_when_none_found(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="красивая квартира у моря")
        )

        result = await analyzer.analyze("красивая квартира у моря")

        assert result["filters"] == {}
        assert result["semantic_query"] == "красивая квартира у моря"

    async def test_analyze_handles_missing_semantic_query_in_response(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={"price": {"lt": 50000}}, semantic_query="")
        )

        original_query = "квартира до 50000 евро"
        result = await analyzer.analyze(original_query)

        assert result["filters"] == {"price": {"lt": 50000}}
        assert result["semantic_query"] == original_query

    async def test_analyze_handles_missing_filters_in_response(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(semantic_query="уютная квартира")
        )

        result = await analyzer.analyze("уютная квартира")

        assert result["filters"] == {}
        assert result["semantic_query"] == "уютная квартира"

    async def test_analyze_with_complex_filters(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={
                    "price": {"lt": 100000, "gt": 50000},
                    "rooms": 2,
                    "city": "Солнечный берег",
                    "area": {"gte": 50},
                    "distance_to_sea": {"lt": 500},
                },
                semantic_query="квартира с хорошим ремонтом",
            )
        )

        result = await analyzer.analyze(
            "2-комнатная квартира от 50000 до 100000 евро в Солнечном берегу"
        )

        assert result["filters"]["price"] == {"lt": 100000, "gt": 50000}
        assert result["filters"]["rooms"] == 2
        assert result["filters"]["city"] == "Солнечный берег"

    async def test_analyze_sets_max_tokens(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="test")
        )

        await analyzer.analyze("test query")

        call_kwargs = analyzer._instructor_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 1000

    async def test_analyze_with_unicode_query(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={"city": "Варна"}, semantic_query="квартира с мебелью"
            )
        )

        result = await analyzer.analyze("Ищу квартиру с мебелью в Варне")

        assert result["filters"]["city"] == "Варна"
        assert result["semantic_query"] == "квартира с мебелью"

    async def test_analyze_handles_instructor_failure(self, analyzer):
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Instructor failed")
        )

        result = await analyzer.analyze("test query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "test query"


# =============================================================================
# TestQueryAnalyzerClose
# =============================================================================


class TestQueryAnalyzerClose:
    """Tests for QueryAnalyzer.close method."""

    async def test_close_calls_close_on_client(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer.client = AsyncMock()

        await analyzer.close()

        analyzer.client.close.assert_called_once()


# =============================================================================
# Integration-style tests (still mocked, but testing flow)
# =============================================================================


class TestQueryAnalyzerFlow:
    """Test typical usage flow of QueryAnalyzer."""

    async def test_full_lifecycle(self):
        analyzer = QueryAnalyzer(
            api_key="test-key", base_url="http://localhost:8000", model="gpt-4o"
        )

        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={"price": {"lt": 75000}}, semantic_query="квартира у моря"
            )
        )
        analyzer.client = AsyncMock()  # needed for close() assertion

        assert analyzer.api_key == "test-key"
        assert analyzer.base_url == "http://localhost:8000"
        assert analyzer.model == "gpt-4o"

        result = await analyzer.analyze("квартира до 75000 евро у моря")
        assert result["filters"] == {"price": {"lt": 75000}}
        assert result["semantic_query"] == "квартира у моря"

        await analyzer.close()
        analyzer.client.close.assert_called_once()

    async def test_multiple_queries(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer._instructor_client = AsyncMock()

        responses = [
            QueryAnalysisResult(filters={"city": "Несебр"}, semantic_query="студия"),
            QueryAnalysisResult(filters={"rooms": 2}, semantic_query="квартира"),
            QueryAnalysisResult(filters={}, semantic_query="апартамент у моря"),
        ]
        analyzer._instructor_client.chat.completions.create = AsyncMock(side_effect=responses)

        result1 = await analyzer.analyze("студия в Несебре")
        result2 = await analyzer.analyze("двухкомнатная квартира")
        result3 = await analyzer.analyze("апартамент у моря")

        assert result1["filters"] == {"city": "Несебр"}
        assert result2["filters"] == {"rooms": 2}
        assert result3["filters"] == {}
        assert analyzer._instructor_client.chat.completions.create.call_count == 3

    async def test_error_recovery(self):
        analyzer = QueryAnalyzer(api_key="test-key", base_url="http://localhost:8000")
        analyzer._instructor_client = AsyncMock()

        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=[
                openai.APIConnectionError(request=MagicMock()),
                QueryAnalysisResult(filters={"city": "Бургас"}, semantic_query="квартира"),
            ]
        )

        result1 = await analyzer.analyze("query1")
        assert result1["filters"] == {}
        assert result1["semantic_query"] == "query1"

        result2 = await analyzer.analyze("query2")
        assert result2["filters"] == {"city": "Бургас"}
        assert result2["semantic_query"] == "квартира"


# =============================================================================
# TestQueryAnalyzerInstructorLangfuseCompat (#1659 STEP 0 PREFLIGHT)
# =============================================================================


class TestQueryAnalyzerInstructorLangfuseCompat:
    """Preflight: confirm `instructor.from_openai(langfuse.openai.AsyncOpenAI(...))`
    preserves langfuse auto-tracing on the underlying client.

    Rationale (audit comment on #1659): if instructor patched
    ``chat.completions.create`` at the wrong layer it would strip the
    ``langfuse.openai`` wrap, and then a plain ``@observe`` wrapper around
    ``QueryAnalyzer.analyze`` would NOT contain a nested generation
    observation — we'd need ``with langfuse.start_as_current_observation
    (as_type='generation', ...)`` instead.

    What this test asserts: the AsyncInstructor instance retains a reference
    to the original langfuse-wrapped client (``ic.client is c``) and that
    client's ``chat.completions.create`` still carries the langfuse wrapt
    marker (``_self_wrapper.__module__`` starts with ``"langfuse.openai"``).
    instructor's ``AsyncInstructor.create`` ultimately delegates to
    ``self.client.chat.completions.create`` via ``self.create_fn`` so the
    langfuse generation is created at call time. Pass ⇒ simple ``@observe``
    is the correct implementation strategy for #1659.
    """

    def test_chat_completions_create_remains_langfuse_wrapped(self):
        """instructor must not strip the langfuse trace wrap on the client."""
        import instructor
        from langfuse.openai import AsyncOpenAI

        c = AsyncOpenAI(api_key="x", base_url="http://x")
        ic = instructor.from_openai(c)

        # instructor stores the original client as ic.client
        assert ic.client is c, (
            "instructor.from_openai must retain the original langfuse-wrapped "
            "client; otherwise the langfuse trace wrap is lost"
        )

        underlying_create = ic.client.chat.completions.create
        # langfuse uses wrapt to monkey-patch the OpenAI SDK call site, leaving
        # a BoundFunctionWrapper whose `_self_wrapper` points back at langfuse.
        assert hasattr(underlying_create, "__wrapped__"), (
            "Expected `__wrapped__` marker from wrapt on langfuse.openai's "
            "patched chat.completions.create"
        )
        wrapper = getattr(underlying_create, "_self_wrapper", None)
        assert wrapper is not None, (
            "Expected wrapt `_self_wrapper` attribute on langfuse-patched create"
        )
        wrapper_module = getattr(wrapper, "__module__", "") or ""
        assert wrapper_module.startswith("langfuse.openai"), (
            f"langfuse trace wrap stripped after instructor.from_openai — "
            f"_self_wrapper module is {wrapper_module!r}; "
            f"#1659 implementation must switch to "
            f"`with langfuse.start_as_current_observation(as_type='generation', "
            f"name='query-analyzer-llm', model=self.model) as gen: ...`"
        )


# =============================================================================
# TestQueryAnalyzerObserveInstrumentation (#1659)
# =============================================================================


class TestQueryAnalyzerObserveInstrumentation:
    """Tests for @observe instrumentation on QueryAnalyzer.analyze (#1659).

    Contract: ``analyze`` (line ~86) must be wrapped with::

        @observe(name="query-analyzer",
                 capture_input=False, capture_output=False)

    so the auto-traced generation produced by ``langfuse.openai.AsyncOpenAI``
    (preserved through ``instructor.from_openai``, see preflight test)
    becomes a child of a named ``query-analyzer`` span instead of an orphan
    top-level trace when the analyzer is invoked outside a request-scoped
    trace.

    CRITICAL: the wrapper MUST NOT use ``as_type="generation"`` —
    ``langfuse.openai`` already creates a generation observation for each
    ``chat.completions.create()`` call (preflight verifies the wrap
    survives), and an outer generation would produce duplicate observations.
    Plain span > nested generation is the intended structure.

    Curated ``update_current_span`` payloads avoid leaking the full query
    or full LLM response into Langfuse. On exception the span is recorded
    at ``level="ERROR"`` with a truncated ``status_message``; the existing
    fallback contract (``return {"filters": {}, "semantic_query": query}``)
    is preserved verbatim.
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Replace get_client used by the query_analyzer module with a recording mock."""
        from telegram_bot.services import query_analyzer as qa_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(qa_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe(monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the @observe decorator with a no-op and reload the module.

        Uses ``monkeypatch.delitem(sys.modules, ...)`` so that after the test
        the original module object is restored — otherwise the reload would
        leave a fresh ``QueryAnalyzer`` class in ``sys.modules`` and other
        tests would see drift between the lazy-imported package attribute
        and any test-file-level binding (pattern from #1660 TDD).
        """
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        monkeypatch.delitem(sys.modules, "telegram_bot.services.query_analyzer", raising=False)
        importlib.import_module("telegram_bot.services.query_analyzer")

    @staticmethod
    def _record_observe_calls(
        monkeypatch: pytest.MonkeyPatch,
    ) -> list[dict[str, object]]:
        """Replace @observe with a recorder and reload the module.

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
        monkeypatch.delitem(sys.modules, "telegram_bot.services.query_analyzer", raising=False)
        importlib.import_module("telegram_bot.services.query_analyzer")
        return captured_calls

    # ------------------------------------------------------------------
    # Module-level wiring
    # ------------------------------------------------------------------

    def test_module_imports_observe_and_get_client(self):
        """Module wires the Langfuse decorator + client accessor (#1659 contract)."""
        from telegram_bot.services import query_analyzer as qa_mod

        assert hasattr(qa_mod, "observe"), (
            "telegram_bot.services.query_analyzer must import `observe` from "
            "telegram_bot.observability for the @observe decorator on "
            "QueryAnalyzer.analyze"
        )
        assert hasattr(qa_mod, "get_client"), (
            "telegram_bot.services.query_analyzer must import `get_client` "
            "from telegram_bot.observability for curated update_current_span calls"
        )

    # ------------------------------------------------------------------
    # Decorator kwargs
    # ------------------------------------------------------------------

    def test_observe_decorator_applied_with_correct_kwargs(self, monkeypatch):
        """``analyze`` is decorated with the audit's exact kwargs.

        CRITICAL: ``as_type`` MUST NOT be present — preflight confirmed
        ``langfuse.openai`` wrap survives ``instructor.from_openai`` (the
        underlying client's chat.completions.create still carries
        ``_self_wrapper.__module__ == "langfuse.openai"``), so the wrapper
        is a plain span and the nested generation is owned by langfuse.openai.
        """
        captured = self._record_observe_calls(monkeypatch)

        matches = [c for c in captured if c.get("name") == "query-analyzer"]
        assert len(matches) == 1, (
            "Expected exactly one @observe(name='query-analyzer', ...) on "
            f"QueryAnalyzer.analyze; observed names: {[c.get('name') for c in captured]}"
        )
        kwargs = matches[0]
        assert kwargs.get("capture_input") is False, (
            "capture_input must be False (issue #1659 explicit kwarg)"
        )
        assert kwargs.get("capture_output") is False, (
            "capture_output must be False (issue #1659 explicit kwarg)"
        )
        assert "as_type" not in kwargs, (
            "Wrapper must NOT use as_type='generation' — langfuse.openai "
            "already creates a generation for each chat.completions.create "
            "(verified by preflight); wrapping the public method as another "
            "generation would produce duplicates."
        )

    # ------------------------------------------------------------------
    # Behavior: input payload (curated)
    # ------------------------------------------------------------------

    async def test_input_payload_is_curated_query_preview_and_model(self, monkeypatch):
        """``analyze`` records {query_preview (<=120), model} only — no full query."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.query_analyzer import (
            QueryAnalysisResult,
            QueryAnalyzer,
        )

        long_query = (
            "Ищу 2-комнатную квартиру в Несебре с видом на море до 100000 "
            "евро, желательно с мебелью, на средних этажах в новостройке "
            "недалеко от пляжа и инфраструктуры — точно длиннее 120 символов"
        )
        assert len(long_query) > 120

        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={}, semantic_query="quartira")
        )

        await analyzer.analyze(long_query)

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "input" in c.kwargs
        ]
        assert input_calls, (
            "update_current_span(input=...) was never called on QueryAnalyzer.analyze"
        )
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert "query_preview" in captured_input
        assert isinstance(captured_input["query_preview"], str)
        assert len(captured_input["query_preview"]) <= 120
        assert captured_input.get("model") == "gpt-4o-mini"

        # Forbidden: full query MUST NOT appear in span input.
        assert long_query not in str(captured_input)

    # ------------------------------------------------------------------
    # Behavior: output payload (curated)
    # ------------------------------------------------------------------

    async def test_output_payload_records_curated_qaresult_summary(self, monkeypatch):
        """``analyze`` records curated summary of QueryAnalysisResult — no full payload.

        ``QueryAnalysisResult`` has two fields: ``filters`` (dict[str, Any])
        and ``semantic_query`` (str). To avoid leaking user query content
        and filter values (which can include city names, exact prices, etc.)
        the curated output captures schema-level metadata only:
        - ``filter_keys``: sorted list of filter dimension names (bounded
          schema enum: price, rooms, city, area, ...). No values.
        - ``filter_count``: number of filters extracted.
        - ``semantic_query_len``: length of the semantic query string. No
          content.
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.query_analyzer import (
            QueryAnalysisResult,
            QueryAnalyzer,
        )

        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        secret_city = "СекретныйГородКоторыйНеДолженПопастьВspan"
        secret_semantic = "очень-чувствительный-семантический-запрос-пользователя"
        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(
                filters={
                    "price": {"lt": 100000},
                    "city": secret_city,
                    "rooms": 2,
                },
                semantic_query=secret_semantic,
            )
        )

        result = await analyzer.analyze("any query")
        # Behavior unchanged: caller still receives full filters + semantic_query
        assert result["filters"]["city"] == secret_city
        assert result["semantic_query"] == secret_semantic

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert output_calls, (
            "update_current_span(output=...) was never called on QueryAnalyzer.analyze"
        )
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert captured_output.get("filter_count") == 3
        assert captured_output.get("filter_keys") == sorted(["price", "city", "rooms"])
        assert captured_output.get("semantic_query_len") == len(secret_semantic)

        # Forbidden: full LLM response payload MUST NOT appear in span output.
        captured_str = str(captured_output)
        assert secret_city not in captured_str, (
            "Full filter values (e.g. city name) must not be captured to span output"
        )
        assert secret_semantic not in captured_str, (
            "Full semantic_query content must not be captured to span output"
        )

    async def test_analyze_works_when_langfuse_client_is_none(self, monkeypatch):
        """Tracing must degrade gracefully when Langfuse is unavailable."""
        self._disable_observe(monkeypatch)

        from telegram_bot.services import query_analyzer as qa_mod
        from telegram_bot.services.query_analyzer import (
            QueryAnalysisResult,
            QueryAnalyzer,
        )

        monkeypatch.setattr(qa_mod, "get_client", lambda: None)

        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            return_value=QueryAnalysisResult(filters={"city": "Бургас"}, semantic_query="квартира")
        )

        result = await analyzer.analyze("квартира в Бургасе")

        assert result == {"filters": {"city": "Бургас"}, "semantic_query": "квартира"}

    # ------------------------------------------------------------------
    # Behavior: exception path
    # ------------------------------------------------------------------

    async def test_exception_path_records_error_level_and_returns_fallback(self, monkeypatch):
        """On internal failure: span level=ERROR + truncated status_message.

        Existing fallback contract is preserved: analyze swallows the
        exception and returns ``{"filters": {}, "semantic_query": query}``.
        The ERROR span is recorded before the fallback is returned.
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.query_analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Instructor exploded mid-analyze")
        )

        original_query = "квартира в Бургасе"
        result = await analyzer.analyze(original_query)

        # Existing fallback contract preserved
        assert result == {"filters": {}, "semantic_query": original_query}

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, (
            "Failure path must call update_current_span(level='ERROR', ...) on "
            "QueryAnalyzer.analyze (#1659 plan)"
        )
        status = error_calls[0].get("status_message", "")
        assert "Instructor exploded mid-analyze" in status
        assert len(status) <= 220

    async def test_exception_path_for_openai_api_errors_records_error_level(self, monkeypatch):
        """OpenAI-specific errors (timeout/connection/rate-limit) also record ERROR.

        Existing code has separate `except (APIConnectionError, RateLimitError,
        APITimeoutError)` and generic `except Exception` branches; both must
        record ERROR before returning the fallback.
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.query_analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer(
            api_key="test-api-key", base_url="http://localhost:8000", model="gpt-4o-mini"
        )
        analyzer._instructor_client = AsyncMock()
        analyzer._instructor_client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )

        original_query = "студия на первой линии"
        result = await analyzer.analyze(original_query)

        assert result == {"filters": {}, "semantic_query": original_query}

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, (
            "OpenAI APITimeoutError branch must also record level='ERROR' on the span"
        )
        status = error_calls[0].get("status_message", "")
        assert isinstance(status, str)
        assert len(status) <= 220
