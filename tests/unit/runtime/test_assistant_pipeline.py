"""Tests for the runtime assistant pipeline seam."""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.contracts import AssistantResult
from src.runtime.generation import GenerationResult


async def test_run_assistant_pipeline_returns_assistant_result(monkeypatch) -> None:
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    async def fake_rag_pipeline(**kwargs):
        return {
            "documents": [
                {
                    "content": "fact",
                    "metadata": {
                        "source_id": "doc-1",
                        "title": "Doc 1",
                        "url": "fixture://doc-1",
                    },
                }
            ],
            "cache_hit": False,
            "query_type": "GENERAL",
            "rerank_applied": True,
        }

    async def fake_generate_answer(_request):
        return GenerationResult(
            payload={
                "response": "answer",
                "llm_provider_model": "fake-model",
                "usage_details": {"input": 1, "output": 2},
            }
        )

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "GENERAL"

    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
        fake_rag_pipeline,
    )
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.generate_answer",
        fake_generate_answer,
    )

    result = await run_assistant_pipeline(
        AssistantRequest(
            query="q",
            user_context=UserContext(user_id="42", session_id="s"),
            request_id="req-1",
        ),
        dependencies=CoreDependencies(
            cache=object(),
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            config=object(),
        ),
    )

    assert result.response_text == "answer"
    assert result.route == "rag_search"
    assert result.retrieved_doc_ids == ["doc-1"]
    assert result.retrieved_sources == [{"title": "Doc 1", "url": "fixture://doc-1"}]
    assert result.llm_model == "fake-model"


# Regression test for #2967: pipeline must not swallow exceptions
async def test_run_assistant_pipeline_propagates_exception(monkeypatch) -> None:
    """Exceptions raised inside the pipeline must propagate, not be swallowed."""
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "GENERAL"
    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)

    async def exploding_rag_pipeline(**kwargs):
        raise RuntimeError("deliberate-test-explosion")

    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
        exploding_rag_pipeline,
    )

    with pytest.raises(RuntimeError, match="deliberate-test-explosion"):
        await run_assistant_pipeline(
            AssistantRequest(
                query="q",
                user_context=UserContext(user_id="42", session_id="s"),
                request_id="req-1",
            ),
            dependencies=CoreDependencies(
                cache=object(),
                embeddings=object(),
                sparse_embeddings=object(),
                qdrant=object(),
                config=object(),
            ),
        )


# ---------------------------------------------------------------------------
# #3208 — core-owned semantic cache store + truthful result metadata
# ---------------------------------------------------------------------------


def _doc() -> dict:
    return {
        "content": "fact",
        "metadata": {"source_id": "doc-1", "title": "Doc 1", "url": "fixture://doc-1"},
        "score": 0.9,
    }


def _cache_store_mocks():
    cache = MagicMock()
    cache.store_semantic = AsyncMock()
    return cache


async def _run(
    *,
    rag_result: dict | None = None,
    generation_payload: dict | None = None,
    cache: Any = None,
    config: Any = None,
    filters: dict | None = None,
) -> AssistantResult:
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    rag = AsyncMock(
        return_value=rag_result
        or {
            "documents": [_doc()],
            "cache_hit": False,
            "query_type": "FAQ",
            "rerank_applied": False,
            "grade_confidence": 0.9,
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }
    )
    gen = AsyncMock(
        return_value=GenerationResult(
            payload=generation_payload
            or {
                "response": "answer",
                "llm_provider_model": "fake-model",
                "usage_details": {"input": 1, "output": 2},
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "safe_fallback_used": False,
                "llm_call_count": 1,
            }
        )
    )

    dependencies = CoreDependencies(
        cache=cache if cache is not None else object(),
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
        config=config if config is not None else object(),
    )
    with (
        patch("src.runtime.routing.classify.classify_query", return_value="FAQ"),
        patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
    ):
        return await run_assistant_pipeline(
            AssistantRequest(
                query="топ студий у моря в Солнечном Берегу",
                user_context=UserContext(
                    user_id="42", session_id="s", role="client", filters=filters
                ),
                request_id="req-3208",
            ),
            dependencies=dependencies,
        )


async def test_surfaces_truthful_cache_safety_metadata() -> None:
    result = await _run()

    assert result.grounded is True
    assert result.legal_answer_safe is True
    assert result.semantic_cache_safe_reuse is True
    assert result.safe_fallback_used is False
    assert result.grounding_mode == "normal"


async def test_stores_semantic_cache_with_filter_signature_and_role() -> None:
    cache = _cache_store_mocks()

    result = await _run(cache=cache, filters={"city": "Несебр"})

    cache.store_semantic.assert_awaited_once()
    kwargs = cache.store_semantic.await_args.kwargs
    assert kwargs["query"] == "топ студий у моря в Солнечном Берегу"
    assert kwargs["response"] == "answer"
    assert kwargs["vector"] == [0.1, 0.2, 0.3]
    assert kwargs["query_type"] == "FAQ"
    assert kwargs["cache_scope"] == "rag"
    assert kwargs["agent_role"] == "client"
    assert kwargs["filter_signature"] == "city=Несебр"
    metadata = kwargs["metadata"]
    assert metadata["grounding_mode"] == "normal"
    assert metadata["semantic_cache_safe_reuse"] is True
    assert metadata["cache_eligible"] is True
    assert result.response_text == "answer"


async def test_strict_unsafe_generation_skips_semantic_store() -> None:
    cache = _cache_store_mocks()

    await _run(
        cache=cache,
        generation_payload={
            "response": "fallback text",
            "llm_provider_model": "safe_fallback",
            "usage_details": None,
            "grounded": False,
            "legal_answer_safe": False,
            "semantic_cache_safe_reuse": False,
            "safe_fallback_used": True,
            "llm_call_count": 0,
        },
    )

    cache.store_semantic.assert_not_awaited()


async def test_provider_fallback_result_skips_semantic_store() -> None:
    cache = _cache_store_mocks()

    await _run(
        cache=cache,
        generation_payload={
            "response": "fallback answer",
            "llm_provider_model": "fallback",
            "usage_details": None,
            "grounded": False,
            "llm_call_count": 1,
            "fallback_used": True,
        },
    )

    cache.store_semantic.assert_not_awaited()


async def test_store_failure_preserves_response() -> None:
    cache = _cache_store_mocks()
    cache.store_semantic = AsyncMock(side_effect=RuntimeError("redis down"))

    result = await _run(cache=cache)

    assert result.response_text == "answer"
    assert result.route == "rag_search"
    assert result.error_type is None


async def test_cache_hit_result_skips_store_and_generation() -> None:
    cache = _cache_store_mocks()

    result = await _run(
        cache=cache,
        rag_result={
            "documents": [],
            "cache_hit": True,
            "response": "cached answer",
            "query_type": "FAQ",
        },
    )

    cache.store_semantic.assert_not_awaited()
    assert result.cache_hit is True
    assert result.route == "cache_hit"
    # Cache hits cannot know generation-time safety verdicts.
    assert result.grounded is None
    assert result.legal_answer_safe is None
    assert result.semantic_cache_safe_reuse is None


async def test_no_store_without_cache_key_embedding() -> None:
    cache = _cache_store_mocks()

    await _run(
        cache=cache,
        rag_result={
            "documents": [_doc()],
            "cache_hit": False,
            "query_type": "FAQ",
            "grade_confidence": 0.9,
        },
    )

    cache.store_semantic.assert_not_awaited()


# Regression #3321: an embedding/BGE dependency failure is a terminal
# controlled result — generation and cache-store must never run.
async def test_embedding_error_is_terminal_dependency_failure(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    generate_calls: list[Any] = []

    async def fake_rag_pipeline(**kwargs):
        return {
            "response": "Service temporarily unavailable",
            "cache_hit": False,
            "documents": [],
            "search_results_count": 0,
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "grade_confidence": 0.0,
            "embeddings_cache_hit": False,
            "embedding_error": True,
            "embedding_error_type": "bge_unavailable",
            "latency_stages": {},
            "rewrite_count": 0,
            "query_type": "GENERAL",
            "retrieved_context": [],
            "semantic_cache_already_checked": False,
        }

    async def failing_generate_answer(_request):
        generate_calls.append(_request)
        raise AssertionError("generation must not run after embedding failure")

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "GENERAL"

    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.rag_pipeline",
        fake_rag_pipeline,
    )
    monkeypatch.setattr(
        "src.runtime.pipeline.assistant_pipeline.generate_answer",
        failing_generate_answer,
    )

    cache = AsyncMock()
    result = await run_assistant_pipeline(
        AssistantRequest(
            query="q",
            user_context=UserContext(user_id="42", session_id="s"),
            request_id="req-embed-fail",
        ),
        dependencies=CoreDependencies(
            cache=cache,
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            config=object(),
        ),
    )

    assert result.response_text == "Service temporarily unavailable"
    assert result.error_type == "bge_unavailable"
    assert result.route != "rag_search"
    assert result.cache_hit is False
    assert generate_calls == []
    cache.assert_not_awaited()


# Regression #3479: a terminal embedding dependency failure must produce
# exactly ONE truthful search outcome — the dependency error — never a
# preceding rag_search success for the same request. Driven through the
# public core entrypoint with a recording telemetry listener and a real
# rag_pipeline whose embedding dependency is down.
async def test_embedding_error_emits_single_dependency_error_search_outcome() -> None:
    from unittest.mock import patch

    from src.core import CoreDependencies, UserContext
    from src.core.assistant import run_assistant_request

    query = "тестовый вопрос по документам поиска"
    rid = "req-3479-embed-outage"

    class _RecordingTelemetry:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict[str, Any]]] = []

        def log_event(self, event: str, **fields: Any) -> None:
            self.events.append((event, dict(fields)))

    class _EmbedOutageEmbeddings:
        async def aembed_query(self, text: str) -> list[float]:
            raise RuntimeError("bge endpoint unavailable")

    class _StubSparseEmbeddings:
        async def aembed_query(self, text: str) -> dict[str, Any]:
            return {}

    class _StubQdrant:
        async def hybrid_search_rrf(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return []

    class _EmbedOutageCache:
        def __init__(self) -> None:
            self.semantic_stores: list[dict[str, Any]] = []

        async def get_embedding(self, key: str) -> list[float] | None:
            return None

        async def check_semantic(self, *args: object, **kwargs: object) -> dict | None:
            return None

        async def store_semantic(self, *args: object, **kwargs: object) -> bool:
            self.semantic_stores.append(dict(kwargs))
            return True

    telemetry = _RecordingTelemetry()
    cache = _EmbedOutageCache()
    generate_calls: list[Any] = []

    async def _generate_must_not_run(request: Any) -> Any:
        generate_calls.append(request)
        raise AssertionError("generation must not run after embedding failure")

    dependencies = CoreDependencies(
        cache=cache,
        embeddings=_EmbedOutageEmbeddings(),
        sparse_embeddings=_StubSparseEmbeddings(),
        qdrant=_StubQdrant(),
        config=object(),
        telemetry=telemetry,
    )

    with patch(
        "src.runtime.pipeline.assistant_pipeline.generate_answer",
        _generate_must_not_run,
    ):
        result = await run_assistant_request(
            query,
            user_context=UserContext(user_id="42", session_id="s"),
            request_id=rid,
            dependencies=dependencies,
        )

    # Terminal embedding-error result (#3321 behavior preserved).
    assert result.route == "dependency_error"
    assert result.error_type

    # COMPLETE ordered event list: one started, ONE search outcome carrying
    # the error category, one completed — no interleaved success.
    assert [(name, fields.get("route")) for name, fields in telemetry.events] == [
        ("assistant_request_started", "unknown"),
        ("search_completed", "dependency_error"),
        ("assistant_request_completed", "dependency_error"),
    ]

    search_events = [
        fields
        for name, fields in telemetry.events
        if name == "search_completed" and fields.get("request_id") == rid
    ]
    assert [fields.get("route") for fields in search_events] == ["dependency_error"]
    assert search_events[0]["error_type"]  # an error category, not a success
    # No raw query text leaked into the outcome payload.
    assert query not in [str(value) for value in search_events[0].values()]

    # No rag_search success outcome for this request.
    assert [
        fields
        for name, fields in telemetry.events
        if name == "search_completed"
        and fields.get("request_id") == rid
        and fields.get("route") == "rag_search"
    ] == []

    assert generate_calls == []
    assert cache.semantic_stores == []


# Regression #3320: grounding policy must be computed BEFORE the semantic
# cache read so strict requests require safe-reuse evidence.
async def test_strict_grounding_policy_reaches_cache_read(monkeypatch) -> None:
    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline import assistant_pipeline

    recorded: dict[str, Any] = {}

    async def fake_rag_pipeline(**kwargs):
        recorded.update(kwargs)
        return {
            "response": "answer",
            "documents": [],
            "cache_hit": False,
            "query_type": "FAQ",
            "rerank_applied": False,
            "grade_confidence": 0.9,
        }

    class _StubGeneration:
        response_text = "answer"
        payload: dict[str, Any] = {
            "grounded": True,
            "usage_details": {},
            "llm_call_count": 1,
        }

    async def fake_generate(_request):
        return _StubGeneration()

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "FAQ"

    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)
    monkeypatch.setattr(assistant_pipeline, "rag_pipeline", fake_rag_pipeline)
    monkeypatch.setattr(assistant_pipeline, "generate_answer", fake_generate)
    monkeypatch.setattr(assistant_pipeline, "get_grounding_mode", lambda **_: "strict")
    await assistant_pipeline.run_assistant_pipeline(
        AssistantRequest(
            query="legal question",
            user_context=UserContext(user_id="42"),
            request_id="req-strict-cache",
        ),
        dependencies=CoreDependencies(
            cache=object(),
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            config=object(),
        ),
    )

    assert recorded["grounding_mode"] == "strict"
    assert recorded["require_safe_reuse"] is True


# Regression #3323: CHITCHAT and OFF_TOPIC never reach the RAG pipeline —
# they return canonical canned responses before any cache/embedding/retrieval/
# LLM side effect.
async def test_chitchat_bypasses_rag_with_canonical_response(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.domain_defaults import CHITCHAT_RESPONSES
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "CHITCHAT"
    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)

    def _fail_rag(**_kwargs):
        raise AssertionError("RAG pipeline must not run for CHITCHAT")

    monkeypatch.setattr("src.runtime.pipeline.assistant_pipeline.rag_pipeline", _fail_rag)

    cache = AsyncMock()
    telemetry = MagicMock()
    result = await run_assistant_pipeline(
        AssistantRequest(
            query="привет",
            user_context=UserContext(user_id="42"),
            request_id="req-chitchat",
        ),
        dependencies=CoreDependencies(
            cache=cache,
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            config=object(),
            telemetry=telemetry,
        ),
    )

    canned = [text for texts in CHITCHAT_RESPONSES.values() for text in texts]
    assert result.response_text in canned
    assert result.route == "non_rag"
    assert result.request_type == "CHITCHAT"
    assert result.request_id == "req-chitchat"
    assert result.cache_hit is False
    cache.assert_not_awaited()

    routed = [
        call
        for call in telemetry.log_event.call_args_list
        if call.args and call.args[0] == "search_completed"
    ]
    assert routed, telemetry.log_event.call_args_list
    assert routed[0].args[1] if len(routed[0].args) > 1 else True


async def test_off_topic_bypasses_rag_with_refusal(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.domain_defaults import OFF_TOPIC_RESPONSES
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    classify_mod = types.ModuleType("src.runtime.routing.classify")
    classify_mod.classify_query = lambda _: "OFF_TOPIC"
    monkeypatch.setitem(sys.modules, "src.runtime.routing.classify", classify_mod)

    def _fail_rag(**_kwargs):
        raise AssertionError("RAG pipeline must not run for OFF_TOPIC")

    monkeypatch.setattr("src.runtime.pipeline.assistant_pipeline.rag_pipeline", _fail_rag)

    result = await run_assistant_pipeline(
        AssistantRequest(
            query="как приготовить борщ",
            user_context=UserContext(user_id="42"),
            request_id="req-offtopic",
        ),
        dependencies=CoreDependencies(
            cache=AsyncMock(),
            embeddings=object(),
            sparse_embeddings=object(),
            qdrant=object(),
            config=object(),
            telemetry=MagicMock(),
        ),
    )

    assert result.response_text in OFF_TOPIC_RESPONSES
    assert result.route == "non_rag"
    assert result.request_type == "OFF_TOPIC"


# ---------------------------------------------------------------------------
# #3491 — request locale reaches generation prompts and semantic cache
# read/store. Identical text with different locales must produce different
# generation instructions, and a semantic cache read/store must always carry
# the request locale so an answer in one language is never served to another.
# ---------------------------------------------------------------------------

_LOCALE_QUERY = "Расскажи что включает в себя комплекс и какая инфраструктура рядом"

# Canonical per-locale generation instructions (#3491).
_LOCALE_INSTRUCTIONS = {
    "ru": "Отвечай на русском языке.",
    "en": "Answer in English.",
    "uk": "Відповідай українською мовою.",
}


class _LocaleRecordingCache:
    """Cache double recording semantic read/store kwargs; always a miss."""

    def __init__(self) -> None:
        self.reads: list[dict[str, Any]] = []
        self.stores: list[dict[str, Any]] = []

    async def get_embedding(self, key: str) -> list[float] | None:
        return None

    async def store_embedding(self, key: str, dense: list[float]) -> None:
        return None

    async def get_sparse_embedding(self, key: str) -> None:
        return None

    async def store_sparse_embedding(self, key: str, sparse: Any) -> None:
        return None

    async def get_search_results(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def store_search_results(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def check_semantic(self, *args: Any, **kwargs: Any) -> str | None:
        self.reads.append(dict(kwargs))
        return None

    async def store_semantic(self, *args: Any, **kwargs: Any) -> bool:
        self.stores.append(dict(kwargs))
        return True


class _LocaleStubEmbeddings:
    async def aembed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


class _LocaleStubSparseEmbeddings:
    async def aembed_query(self, text: str) -> dict[str, Any]:
        return {}


class _LocaleStubQdrant:
    async def hybrid_search_rrf(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class _RecordingLLM:
    """LLM double that records the exact messages sent to the provider."""

    def __init__(self, calls: list[list[dict[str, str]]]) -> None:
        self._calls = calls

    async def completion(self, *, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        self._calls.append([dict(message) for message in messages])
        return types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(message=types.SimpleNamespace(content="Тестовый ответ"))
            ],
            model="locale-test-model",
            usage=types.SimpleNamespace(completion_tokens=10),
        )


def _locale_dependencies(cache: Any, llm_calls: list[list[dict[str, str]]]) -> Any:
    """Core dependencies with real prompt/cache policies; only externals stubbed."""
    from src.core import CoreDependencies

    config = MagicMock()
    config.show_sources = False
    config.response_style_enabled = False
    config.response_style_shadow_mode = False
    config.generate_max_tokens = 512
    config.domain = "real-estate"
    config.llm_temperature = 0.2
    config.llm_model = "locale-test-model"
    config.get_reasoning_kwargs.return_value = {}
    config.create_llm.return_value = _RecordingLLM(llm_calls)
    return CoreDependencies(
        cache=cache,
        embeddings=_LocaleStubEmbeddings(),
        sparse_embeddings=_LocaleStubSparseEmbeddings(),
        qdrant=_LocaleStubQdrant(),
        config=config,
    )


async def test_request_locale_drives_generation_prompt_and_cache_read() -> None:
    """#3491 boundary: ru/en/uk requests with identical text get corresponding
    generation instructions, and every semantic-cache read carries the request
    locale. Driven through the public core entrypoint with real prompt and
    cache policies; only cache/embeddings/qdrant/LLM externals are stubbed."""
    from src.core import UserContext
    from src.core.assistant import run_assistant_request

    prompts_by_language: dict[str, str] = {}

    for locale in ("ru", "en", "uk"):
        llm_calls: list[list[dict[str, str]]] = []
        cache = _LocaleRecordingCache()
        result = await run_assistant_request(
            _LOCALE_QUERY,
            user_context=UserContext(user_id="42", session_id="s", language=locale),
            request_id=f"req-3491-{locale}",
            dependencies=_locale_dependencies(cache, llm_calls),
        )

        assert result.error_type is None, f"harness failure for locale={locale}"
        assert len(llm_calls) == 1, f"generation must run exactly once for locale={locale}"
        system_prompt = llm_calls[0][0]["content"]
        prompts_by_language[locale] = system_prompt
        # The request locale reaches the LLM as a per-locale instruction.
        assert _LOCALE_INSTRUCTIONS[locale] in system_prompt, (
            f"generation prompt must carry the {locale} instruction"
        )
        # Different locales must produce different prompts for identical text.
        assert len(set(prompts_by_language.values())) == len(prompts_by_language)
        # The semantic cache read carries the request locale.
        assert cache.reads, f"semantic cache read must happen for locale={locale}"
        assert cache.reads[0].get("language") == locale, (
            f"semantic cache read must be isolated by locale={locale}"
        )


async def test_unsupported_locale_falls_back_consistently() -> None:
    """#3491: a missing/unsupported locale falls back to one canonical code for
    both the prompt instruction and the semantic-cache read."""
    from src.core import UserContext
    from src.core.assistant import run_assistant_request

    llm_calls: list[list[dict[str, str]]] = []
    cache = _LocaleRecordingCache()
    result = await run_assistant_request(
        _LOCALE_QUERY,
        user_context=UserContext(user_id="42", session_id="s", language="de"),
        request_id="req-3491-unsupported",
        dependencies=_locale_dependencies(cache, llm_calls),
    )

    assert result.error_type is None, "harness failure for unsupported locale"
    assert len(llm_calls) == 1
    system_prompt = llm_calls[0][0]["content"]
    assert _LOCALE_INSTRUCTIONS["ru"] in system_prompt
    assert _LOCALE_INSTRUCTIONS["en"] not in system_prompt
    assert cache.reads, "semantic cache read must happen"
    assert cache.reads[0].get("language") == "ru"


async def test_request_locale_reaches_semantic_cache_store() -> None:
    """#3491: the core-owned semantic cache store carries the same request
    locale as the read, so a stored answer can never be reused for another
    language. Store policy stays real; only rag/generation seams are stubbed
    to make the store eligible (the established #3208 pattern)."""
    from unittest.mock import AsyncMock, patch

    from src.core import AssistantRequest, CoreDependencies, UserContext
    from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline

    rag = AsyncMock(
        return_value={
            "documents": [_doc()],
            "cache_hit": False,
            "query_type": "FAQ",
            "rerank_applied": False,
            "grade_confidence": 0.9,
            "cache_key_embedding": [0.1, 0.2, 0.3],
        }
    )
    gen = AsyncMock(
        return_value=GenerationResult(
            payload={
                "response": "english answer",
                "llm_provider_model": "fake-model",
                "usage_details": {"input": 1, "output": 2},
                "grounded": True,
                "legal_answer_safe": True,
                "semantic_cache_safe_reuse": True,
                "safe_fallback_used": False,
                "llm_call_count": 1,
            }
        )
    )
    cache = _LocaleRecordingCache()
    dependencies = CoreDependencies(
        cache=cache,
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
        config=object(),
    )
    with (
        patch("src.runtime.routing.classify.classify_query", return_value="FAQ"),
        patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
    ):
        await run_assistant_pipeline(
            AssistantRequest(
                query=_LOCALE_QUERY,
                user_context=UserContext(user_id="42", session_id="s", language="en"),
                request_id="req-3491-store",
            ),
            dependencies=dependencies,
        )

    assert cache.stores, "eligible generation must store to the semantic cache"
    assert cache.stores[0].get("language") == "en"


async def test_parallel_requests_in_different_languages_stay_isolated() -> None:
    """#3491: concurrent ru/en requests sharing one config, cache, and LLM
    boundary observe their own locale only — the request locale is never
    written into shared config and prompts never bleed across languages."""
    import asyncio

    from src.core import UserContext
    from src.core.assistant import run_assistant_request

    llm_calls: list[list[dict[str, str]]] = []
    cache = _LocaleRecordingCache()
    deps = _locale_dependencies(cache, llm_calls)

    async def _run(locale: str) -> None:
        result = await run_assistant_request(
            _LOCALE_QUERY,
            user_context=UserContext(user_id="42", session_id="s", language=locale),
            request_id=f"req-3491-parallel-{locale}",
            dependencies=deps,
        )
        assert result.error_type is None, f"harness failure for locale={locale}"

    await asyncio.gather(_run("ru"), _run("en"))

    assert len(llm_calls) == 2
    prompts = [call[0]["content"] for call in llm_calls]
    assert prompts[0] != prompts[1]
    # Exactly one request saw each locale instruction — no cross-language bleed.
    assert sum(_LOCALE_INSTRUCTIONS["ru"] in prompt for prompt in prompts) == 1
    assert sum(_LOCALE_INSTRUCTIONS["en"] in prompt for prompt in prompts) == 1
    # Each semantic-cache read was isolated under its own request locale.
    assert {call.get("language") for call in cache.reads} == {"ru", "en"}
    # The shared config object was only read, never mutated per request.
    assert deps.config.llm_model == "locale-test-model"
    assert deps.config.create_llm.call_count == 2
