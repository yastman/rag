"""Characterization lock for grounded knowledge Q&A and safe no-answer (#3200).

Freezes the client-visible core contract (``run_assistant_request`` →
``AssistantResult``) for the demo pair plus the failure modes the demo depends
on:

  - Known-corpus question → grounded answer with real source attribution.
  - Unsupported question → explicit safe/no-answer response, no fabrication.
  - Provider failure (LLM, retrieval) → user-safe text, never a fabricated
    answer or source.
  - Cache hit/miss → identical safety semantics, exactly one answer.
  - Strict legal (high-risk topic) grounding → deterministic safe fallback.

DEP-FREE: stdlib + pytest + unittest.mock only.
OFFLINE:  no live Qdrant, BGE-M3, LLM, or Redis required. Retrieval is stubbed
at the ``rag_pipeline`` seam and the LLM transport is a canned stub; the
grounding policy, generation service, and assistant pipeline run for real.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.contracts import CoreDependencies
from src.retrieval.topic_classifier import TopicLabel, get_query_topic_hint
from src.runtime.generation.policy import _build_fallback_response
from src.runtime.grounding.policy import get_grounding_mode


pytestmark = pytest.mark.characterization

# ---------------------------------------------------------------------------
# Demo lock pair (issue #3200) — FIXED. These are the frozen anchors.
# ---------------------------------------------------------------------------

# 1) Known-corpus question with expected source attribution.
KNOWN_CORPUS_QUESTION = "Сколько стоит студия у моря в Sunny Beach?"
KNOWN_CORPUS_DOC_ID = "sunny_beach_studio"
KNOWN_CORPUS_EXPECTED_SOURCE = {
    "title": "Sunny Beach Studio",
    "url": "fixture://sunny_beach_studio",
}
KNOWN_CORPUS_GROUNDED_ANSWER = "Стоимость студии в Sunny Beach — 115 000 EUR, бассейн включён."

# 2) Unsupported question with an explicit safe/no-answer response.
UNSUPPORTED_QUESTION = "Найди замок в Софии с частным аэропортом и вертолётной площадкой"
UNSUPPORTED_NO_CLAIM_ANSWER = (
    "В базе нет информации по этому запросу. Уточните, пожалуйста, вопрос."
)

# Unanswerable high-risk (legal) question → strict grounding safe fallback.
LEGAL_UNANSWERABLE_QUESTION = "Какие документы нужны для ВНЖ на несуществующем острове в базе?"

# Frozen explicit safe/no-answer responses (generation policy builders — these,
# NOT the grounding-policy helper texts, are what strict fallback actually
# returns on the live path).
_SAFE_NO_ANSWER_TEXT = (
    "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."
)
_SAFE_WITH_WEAK_DOCS_TEXT = (
    "⚠️ Сервис генерации ответов временно недоступен.\n\n"
    "Найденные результаты:\n\n"
    "1. **Sunny Beach Studio**\n\n"
    "Напишите менеджеру для получения детальной информации."
)
_RETRIEVAL_ERROR_TEXT = "Сервис временно недоступен. Пожалуйста, повторите через минуту."


def _known_doc() -> dict[str, Any]:
    """The known-corpus document backing KNOWN_CORPUS_QUESTION."""
    return {
        "content": (
            "Sunny Beach studio apartment, 42 m², sea view, pool included. Price: 115 000 EUR."
        ),
        "metadata": {
            "source_id": KNOWN_CORPUS_DOC_ID,
            "title": KNOWN_CORPUS_EXPECTED_SOURCE["title"],
            "url": KNOWN_CORPUS_EXPECTED_SOURCE["url"],
        },
        "score": 0.93,
    }


# ---------------------------------------------------------------------------
# Deterministic offline collaborators
# ---------------------------------------------------------------------------


class _CannedLLM:
    """LLM transport stub returning a canned answer and counting calls."""

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.create_calls = 0
        self.completion = self._create

    async def _create(self, **_kwargs: Any) -> Any:
        self.create_calls += 1
        return SimpleNamespace(
            model="canned-characterization-llm",
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=48, total_tokens=168),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._answer))],
        )


class _CannedLLMConfig:
    """GraphConfig-compatible config serving ``_CannedLLM`` (or failing)."""

    domain = "недвижимость в Болгарии"
    llm_model = "canned-characterization-llm"
    llm_temperature = 0.0
    generate_max_tokens = 512
    streaming_enabled = False
    show_sources = False
    response_style_enabled = False
    response_style_shadow_mode = False

    def __init__(self, answer: str = "", *, fail: bool = False) -> None:
        self._fail = fail
        self.llm = _CannedLLM(answer)

    def create_llm(self, *, auto_trace: bool = False) -> Any:
        if self._fail:
            raise TimeoutError("llm provider unavailable")
        return self.llm

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        return {}


def _characterization_dyn() -> dict[str, Any]:
    """Hermetic replacements for the dynamic generation modules."""
    detector = MagicMock()
    detector.detect.return_value = SimpleNamespace(
        style="balanced", difficulty="medium", reasoning="characterization", word_count=7
    )
    return {
        "ResponseStyleDetector": lambda: detector,
        "detect_coverage_mode": lambda _q: SimpleNamespace(needs_coverage=False, reason=None),
        "get_prompt_with_config": lambda name, **_kw: (f"sys::{name}", {"max_tokens": 300}),
        "get_prompt_with_object": lambda _n, **_kw: (None, None),
        "build_system_prompt_with_manager": lambda **_kw: "style_sys_characterization",
        "get_token_limit": lambda _s, _d: 512,
        "PipelineMetrics": MagicMock(get=MagicMock(return_value=MagicMock(record=MagicMock()))),
    }


def _rag_stub(
    documents: list[dict[str, Any]],
    *,
    cache_hit: bool = False,
    response: str = "",
    grade_confidence: float = 0.9,
    side_effect: Exception | None = None,
) -> AsyncMock:
    """Deterministic rag_pipeline stub at the assistant-pipeline seam."""
    if side_effect is not None:
        return AsyncMock(side_effect=side_effect)
    return AsyncMock(
        return_value={
            "documents": documents,
            "cache_hit": cache_hit,
            "response": response,
            "search_results_count": len(documents),
            "rerank_applied": False,
            "query_type": "GENERAL",
            "grade_confidence": grade_confidence,
        }
    )


async def _run_boundary(
    query: str,
    *,
    config: _CannedLLMConfig,
    rag: AsyncMock,
    request_id: str,
) -> Any:
    """Run one question through the real core boundary with stubbed seams."""
    from src.core.assistant import run_assistant_request

    dependencies = CoreDependencies(
        cache=object(),
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
        reranker=None,
        llm=None,
        config=config,
    )
    with (
        patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
        patch(
            "src.runtime.generation.service._get_dynamic_modules",
            lambda _extra=None: _characterization_dyn(),
        ),
    ):
        return await run_assistant_request(
            query,
            dependencies=dependencies,
            request_id=request_id,
        )


# ---------------------------------------------------------------------------
# 1) Known-corpus question → grounded answer with real source attribution
# ---------------------------------------------------------------------------


class TestKnownCorpusGroundedAnswer:
    """Acceptance: known-corpus input produces a grounded answer with a real source."""

    async def test_known_question_returns_grounded_answer_with_source(self) -> None:
        config = _CannedLLMConfig(KNOWN_CORPUS_GROUNDED_ANSWER)
        rag = _rag_stub([_known_doc()])

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3200-known"
        )

        assert result.route == "rag_search"
        assert result.response_text == KNOWN_CORPUS_GROUNDED_ANSWER
        assert result.retrieved_doc_ids == [KNOWN_CORPUS_DOC_ID]
        assert result.retrieved_sources == [KNOWN_CORPUS_EXPECTED_SOURCE]
        assert result.documents_count == 1
        assert result.error_type is None

    async def test_known_question_records_metadata_at_core_boundary(self) -> None:
        """Grounding, source, model, usage, and safe-fallback flags are surfaced."""
        config = _CannedLLMConfig(KNOWN_CORPUS_GROUNDED_ANSWER)
        rag = _rag_stub([_known_doc()])

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3200-metadata"
        )

        assert result.grounding_mode == "normal"
        assert result.grounded is True
        assert result.safe_fallback_used is False
        assert result.llm_model == "canned-characterization-llm"
        assert result.llm_call_count == 1
        assert result.usage == {"input": 120, "output": 48, "total": 168}
        assert result.cache_hit is False

    async def test_known_question_generates_exactly_one_answer(self) -> None:
        """One question → one pipeline run, one LLM call, one answer text."""
        config = _CannedLLMConfig(KNOWN_CORPUS_GROUNDED_ANSWER)
        rag = _rag_stub([_known_doc()])

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3200-one-answer"
        )

        rag.assert_awaited_once()
        assert config.llm.create_calls == 1
        assert isinstance(result.response_text, str)
        assert result.response_text


# ---------------------------------------------------------------------------
# 2) Unsupported question → explicit safe/no-answer, never a fabrication
# ---------------------------------------------------------------------------


class TestUnsupportedQuestionNoFabrication:
    """Acceptance: unsupported inputs never fabricate an answer or a source."""

    async def test_unsupported_question_surfaces_no_sources_and_no_docs(self) -> None:
        """Empty retrieval → no doc IDs/sources at the boundary even when the
        model produces a no-claim answer in normal grounding mode."""
        config = _CannedLLMConfig(UNSUPPORTED_NO_CLAIM_ANSWER)
        rag = _rag_stub([], grade_confidence=0.0)

        result = await _run_boundary(
            UNSUPPORTED_QUESTION, config=config, rag=rag, request_id="i3200-unsupported"
        )

        assert result.retrieved_doc_ids == []
        assert result.retrieved_sources == []
        assert result.documents_count == 0
        assert result.response_text == UNSUPPORTED_NO_CLAIM_ANSWER
        assert result.error_type is None
        assert config.llm.create_calls == 1

    async def test_unsupported_legal_question_returns_explicit_safe_no_answer(self) -> None:
        """High-risk topic + empty retrieval → deterministic safe fallback, no LLM."""
        config = _CannedLLMConfig("этот ответ не должен попасть в результат")
        rag = _rag_stub([], grade_confidence=0.1)

        result = await _run_boundary(
            LEGAL_UNANSWERABLE_QUESTION, config=config, rag=rag, request_id="i3200-legal-safe"
        )

        assert result.response_text == _SAFE_NO_ANSWER_TEXT
        assert result.safe_fallback_used is True
        assert result.grounded is False
        assert result.grounding_mode == "strict"
        assert result.llm_model == "safe_fallback"
        assert result.llm_call_count == 0
        assert result.retrieved_doc_ids == []
        assert result.retrieved_sources == []
        assert result.documents_count == 0
        assert config.llm.create_calls == 0, "LLM must never be consulted for the safe fallback"

    async def test_strict_legal_with_low_confidence_docs_falls_back_without_llm(self) -> None:
        """Strict mode + weak evidence → fallback text; real sources still attributed."""
        config = _CannedLLMConfig("этот ответ не должен попасть в результат")
        rag = _rag_stub([_known_doc()], grade_confidence=0.2)

        result = await _run_boundary(
            LEGAL_UNANSWERABLE_QUESTION, config=config, rag=rag, request_id="i3200-legal-weak"
        )

        assert result.response_text == _SAFE_WITH_WEAK_DOCS_TEXT
        assert result.safe_fallback_used is True
        assert result.grounded is False
        assert config.llm.create_calls == 0
        # The retrieved source is a real retrieval fact, not a fabrication.
        assert result.retrieved_doc_ids == [KNOWN_CORPUS_DOC_ID]
        assert result.retrieved_sources == [KNOWN_CORPUS_EXPECTED_SOURCE]


# ---------------------------------------------------------------------------
# 3) Provider failure — never a fabricated answer or source
# ---------------------------------------------------------------------------


class TestProviderFailure:
    """Characterize LLM and retrieval provider failures at the core boundary."""

    async def test_llm_provider_failure_answers_fallback_without_model_claim(self) -> None:
        config = _CannedLLMConfig(fail=True)
        rag = _rag_stub([_known_doc()])

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3200-llm-down"
        )

        assert result.response_text == _build_fallback_response([_known_doc()])
        assert result.llm_model == "fallback"
        assert result.grounded is False
        assert result.safe_fallback_used is False
        assert result.llm_call_count == 1
        assert result.usage == {}
        assert result.error_type is None, "provider failure is recoverable, not an error result"
        assert result.retrieved_sources == [KNOWN_CORPUS_EXPECTED_SOURCE]

    async def test_retrieval_provider_failure_returns_user_safe_error(self) -> None:
        rag = _rag_stub([], side_effect=TimeoutError("qdrant unavailable"))

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION,
            config=_CannedLLMConfig("unused"),
            rag=rag,
            request_id="i3200-retrieval-down",
        )

        assert result.route == "error"
        assert result.error_type == "dependency_failed"
        assert "qdrant unavailable" in (result.error_message or "")
        assert result.response_text == _RETRIEVAL_ERROR_TEXT
        assert result.retrieved_doc_ids == []
        assert result.retrieved_sources == []
        assert result.llm_call_count == 0
        assert result.grounded is None
        assert result.safe_fallback_used is False


# ---------------------------------------------------------------------------
# 4) Cache hit/miss — same safety semantics, exactly one answer
# ---------------------------------------------------------------------------


class TestCacheHitMissSafetySemantics:
    """Acceptance: cache hit/miss preserves safety semantics and one answer."""

    async def test_cache_hit_returns_cached_answer_without_generation_or_sources(self) -> None:
        cached_text = "Студия в Sunny Beach — 115 000 EUR (из кэша)."
        config = _CannedLLMConfig("LLM не должен вызываться")
        rag = _rag_stub([], cache_hit=True, response=cached_text)

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3200-cache-hit"
        )

        assert result.route == "cache_hit"
        assert result.cache_hit is True
        assert result.response_text == cached_text
        assert result.error_type is None
        assert result.llm_model is None
        assert result.llm_call_count == 0
        assert config.llm.create_calls == 0
        assert result.retrieved_doc_ids == []
        assert result.retrieved_sources == []
        assert result.safe_fallback_used is False
        assert result.grounded is None
        assert result.usage == {}

    async def test_cache_miss_runs_generation_exactly_once(self) -> None:
        config = _CannedLLMConfig(KNOWN_CORPUS_GROUNDED_ANSWER)
        rag = _rag_stub([_known_doc()])

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3200-cache-miss"
        )

        assert result.route == "rag_search"
        assert result.cache_hit is False
        assert result.response_text == KNOWN_CORPUS_GROUNDED_ANSWER
        assert result.llm_call_count == 1
        assert config.llm.create_calls == 1
        assert result.retrieved_sources == [KNOWN_CORPUS_EXPECTED_SOURCE]


# ---------------------------------------------------------------------------
# 5) Strict grounding topic policy — frozen semantics
# ---------------------------------------------------------------------------


class TestStrictGroundingTopicPolicy:
    """Freeze which topics force strict grounding for the demo."""

    def test_high_risk_topics_are_strict(self) -> None:
        assert get_grounding_mode(query_type="FAQ", topic_hint="legal") == "strict"
        assert get_grounding_mode(query_type="GENERAL", topic_hint="relocation") == "strict"
        assert get_grounding_mode(query_type="FAQ", topic_hint="immigration") == "strict"
        assert get_grounding_mode(query_type="LEGAL", topic_hint=None) == "strict"

    def test_general_and_finance_topics_stay_normal(self) -> None:
        """Frozen current semantics: the finance topic hint is NOT strict.

        If a later demo change moves finance under strict grounding, this
        characterization must be updated deliberately.
        """
        assert get_grounding_mode(query_type="GENERAL", topic_hint=None) == "normal"
        assert get_grounding_mode(query_type="FAQ", topic_hint="finance") == "normal"

    def test_demo_questions_route_to_expected_topics(self) -> None:
        assert get_query_topic_hint(LEGAL_UNANSWERABLE_QUESTION) == TopicLabel.LEGAL
        assert get_query_topic_hint(UNSUPPORTED_QUESTION) is None
        assert get_query_topic_hint(KNOWN_CORPUS_QUESTION) is None


# ---------------------------------------------------------------------------
# #3360: empty provider output is never a grounded, cache-safe success.
# ---------------------------------------------------------------------------


class TestEmptyProviderOutput:
    """None/whitespace/sanitizer-emptied content takes the nonempty fallback."""

    async def _run(self, canned_content: str | None, request_id: str) -> Any:
        config = _CannedLLMConfig(canned_content)
        rag = _rag_stub([_known_doc()])

        with patch(
            "src.runtime.generation.service._sanitize_response_text",
            lambda _t, **_kw: "",
        ):
            return await _run_boundary(
                KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id=request_id
            )

    async def test_none_content_returns_nonempty_fallback(self) -> None:
        result = await self._run(None, "i3360-none")

        assert result.response_text.strip()
        assert result.grounded is False
        assert result.safe_fallback_used is False
        assert result.semantic_cache_safe_reuse is False
        assert result.cache_hit is False

    async def test_whitespace_content_returns_nonempty_fallback(self) -> None:
        result = await self._run("   ", "i3360-whitespace")

        assert result.response_text.strip()
        assert result.grounded is False
        assert result.semantic_cache_safe_reuse is False

    async def test_sanitizer_emptied_content_returns_nonempty_fallback(self) -> None:
        """Provider returned text, but the sanitizer emptied it — same contract."""
        config = _CannedLLMConfig("<script>steal secrets</script>")
        rag = _rag_stub([_known_doc()])

        with patch(
            "src.runtime.generation.service._sanitize_response_text",
            lambda _t, **_kw: "",
        ):
            result = await _run_boundary(
                KNOWN_CORPUS_QUESTION,
                config=config,
                rag=rag,
                request_id="i3360-sanitized",
            )

        assert result.response_text.strip()
        assert result.grounded is False
        assert result.semantic_cache_safe_reuse is False

    async def test_fallback_flags_match_streaming_semantics(self) -> None:
        """Sync and streaming share the same terminal fallback flags (#3360)."""
        config = _CannedLLMConfig(None)
        rag = _rag_stub([_known_doc()])

        result = await _run_boundary(
            KNOWN_CORPUS_QUESTION, config=config, rag=rag, request_id="i3360-parity"
        )

        # Terminal flags identical to the streaming path's empty-output
        # rejection: not grounded, not safe for reuse, fallback text sent.
        assert result.grounded is False
        assert result.safe_fallback_used is False
        assert result.semantic_cache_safe_reuse is False
        assert result.response_text.strip()
