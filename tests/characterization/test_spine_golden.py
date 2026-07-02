"""Characterization (golden) tests for the RAG spine.

Purpose: behavior snapshot BEFORE risky refactors touch these three functions:
  - run_assistant_request  (src/core/assistant.py)
  - _hybrid_retrieve       (src/runtime/pipeline/_cache_stage.py)
  - generate_answer        (src/runtime/generation/service.py)

Golden values are derived from fixed fixture docs + fixed queries.
If a refactor changes behavior the delta shows up here — diff = 0 means
the refactor is behavior-preserving.

DEP-FREE: stdlib + pytest + unittest.mock only.
OFFLINE:  no live Qdrant, BGE-M3, LLM, or Redis required.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.contracts import CoreDependencies
from src.runtime.generation import GenerationResult
from src.runtime.generation.contracts import GenerationRequest
from src.runtime.generation.service import generate_answer
from src.runtime.pipeline._cache_stage import _hybrid_retrieve
from src.runtime.services.coverage_mode import CoverageDecision
from src.runtime.services.response_style_detector import StyleInfo


pytestmark = pytest.mark.characterization

# ---------------------------------------------------------------------------
# Fixture corpus — FIXED.  Do not change; these are the golden anchors.
# ---------------------------------------------------------------------------

_DOC_SUNNY_BEACH = {
    "content": "Sunny Beach studio apartment, 42 m², sea view, pool included. Price: 115 000 EUR.",
    "metadata": {
        "source_id": "doc_sunny_beach_studio",
        "title": "Sunny Beach Studio",
        "url": "fixture://sunny_beach_studio",
    },
    "score": 0.93,
}

_DOC_CLEANING = {
    "content": "Professional cleaning service available. Cost: 30 EUR per visit. Book 48 h in advance.",
    "metadata": {
        "source_id": "doc_cleaning_service",
        "title": "Cleaning Service",
        "url": "fixture://cleaning_service",
    },
    "score": 0.85,
}

_DOC_LEGAL = {
    "content": "Title deed (акт 16) issued. Legal status: completed. Notary transfer in 2 business days.",
    "metadata": {
        "source_id": "doc_legal_status",
        "title": "Legal Status",
        "url": "fixture://legal_status",
    },
    "score": 0.78,
}

_FIXTURE_CORPUS = [_DOC_SUNNY_BEACH, _DOC_CLEANING, _DOC_LEGAL]

# Fixed query used throughout all golden tests
_GOLDEN_QUERY = "Какова стоимость апартаментов и правовой статус объекта?"

# Golden file path — stored alongside tests for diff visibility
_GOLDEN_DIR = Path(__file__).parent / "golden"


def _read_golden(name: str) -> dict:
    """Load golden snapshot; create directory on first run."""
    path = _GOLDEN_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_golden(name: str, data: dict) -> None:
    """Persist golden snapshot."""
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = _GOLDEN_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers — shared mock factories
# ---------------------------------------------------------------------------


def _fake_deps() -> CoreDependencies:
    return CoreDependencies(
        cache=object(),
        embeddings=object(),
        sparse_embeddings=object(),
        qdrant=object(),
    )


def _rag_mock(docs: list[dict]) -> AsyncMock:
    """Deterministic rag_pipeline stub returning fixed docs."""
    return AsyncMock(
        return_value={
            "documents": docs,
            "cache_hit": False,
            "response": "",
            "search_results_count": len(docs),
            "rerank_applied": False,
            "query_type": "GENERAL",
        }
    )


def _gen_mock(text: str) -> AsyncMock:
    """Deterministic generate_answer stub returning fixed answer text."""
    return AsyncMock(
        return_value=GenerationResult(
            payload={
                "response": text,
                "llm_provider_model": "golden-model",
                "llm_call_count": 1,
                "grounded": True,
                "safe_fallback_used": False,
            }
        )
    )


# ---------------------------------------------------------------------------
# 1. run_assistant_request — golden: answer shape + doc IDs + route
# ---------------------------------------------------------------------------


class TestRunAssistantRequestGolden:
    """Golden characterization for run_assistant_request end-to-end shape."""

    @pytest.mark.asyncio
    async def test_golden_answer_non_empty(self) -> None:
        """Golden: answer text must be non-empty for a query with retrieved docs."""
        from src.core.assistant import run_assistant_request

        expected_answer = (
            "Стоимость апартаментов составляет 115 000 EUR. Правовой статус: акт 16 выдан."
        )
        rag = _rag_mock(_FIXTURE_CORPUS)
        gen = _gen_mock(expected_answer)

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                _GOLDEN_QUERY,
                collection="golden_collection",
                dependencies=_fake_deps(),
                request_id="golden-001",
            )

        assert result.response_text != "", "Golden: response_text must be non-empty"
        assert result.response_text == expected_answer

    @pytest.mark.asyncio
    async def test_golden_route_is_rag_search(self) -> None:
        """Golden: route must be 'rag_search' when docs are retrieved."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock(_FIXTURE_CORPUS)
        gen = _gen_mock("Golden answer text.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                _GOLDEN_QUERY,
                collection="golden_collection",
                dependencies=_fake_deps(),
            )

        assert result.route == "rag_search", (
            f"Golden: expected route='rag_search', got '{result.route}'"
        )

    @pytest.mark.asyncio
    async def test_golden_retrieved_doc_ids(self) -> None:
        """Golden: all fixture doc source_ids must surface in retrieved_doc_ids."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock(_FIXTURE_CORPUS)
        gen = _gen_mock("Three documents retrieved.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                _GOLDEN_QUERY,
                collection="golden_collection",
                dependencies=_fake_deps(),
            )

        expected_ids = {"doc_sunny_beach_studio", "doc_cleaning_service", "doc_legal_status"}
        actual_ids = set(result.retrieved_doc_ids)
        assert actual_ids == expected_ids, (
            f"Golden doc IDs mismatch.\n  expected: {sorted(expected_ids)}\n  got: {sorted(actual_ids)}"
        )

    @pytest.mark.asyncio
    async def test_golden_documents_count(self) -> None:
        """Golden: documents_count must equal fixture corpus size (3)."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock(_FIXTURE_CORPUS)
        gen = _gen_mock("Count check.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                _GOLDEN_QUERY,
                collection="golden_collection",
                dependencies=_fake_deps(),
            )

        assert result.documents_count == 3, (
            f"Golden: expected documents_count=3, got {result.documents_count}"
        )

    @pytest.mark.asyncio
    async def test_golden_no_error(self) -> None:
        """Golden: error_type must be None on a successful pipeline run."""
        from src.core.assistant import run_assistant_request

        rag = _rag_mock(_FIXTURE_CORPUS)
        gen = _gen_mock("No errors.")

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                _GOLDEN_QUERY,
                collection="golden_collection",
                dependencies=_fake_deps(),
            )

        assert result.error_type is None, (
            f"Golden: expected error_type=None, got {result.error_type!r}"
        )

    @pytest.mark.asyncio
    async def test_golden_snapshot_shape(self) -> None:
        """Golden file snapshot: write on first run, compare on subsequent runs.

        The snapshot captures the stable structural fields of AssistantResult.
        A refactor that shifts field names, doc ID wiring, or route logic will
        produce a diff here — golden diff = 0 means behavior-preserving.
        """
        from src.core.assistant import run_assistant_request

        answer = "Стоимость 115 000 EUR. Правовой статус: акт 16."
        rag = _rag_mock(_FIXTURE_CORPUS)
        gen = _gen_mock(answer)

        with (
            patch("src.runtime.graph.nodes.classify.classify_query", return_value="GENERAL"),
            patch("src.runtime.pipeline.assistant_pipeline.rag_pipeline", rag),
            patch("src.runtime.pipeline.assistant_pipeline.generate_answer", gen),
        ):
            result = await run_assistant_request(
                _GOLDEN_QUERY,
                collection="golden_collection",
                dependencies=_fake_deps(),
                request_id="golden-snapshot-001",
            )

        snapshot = {
            "response_text": result.response_text,
            "route": result.route,
            "retrieved_doc_ids": sorted(result.retrieved_doc_ids),
            "documents_count": result.documents_count,
            "cache_hit": result.cache_hit,
            "error_type": result.error_type,
        }

        golden_name = "run_assistant_request.json"
        existing = _read_golden(golden_name)
        if not existing:
            # First run: write the golden file
            _write_golden(golden_name, snapshot)
            return  # Pass on first write

        assert snapshot == existing, (
            f"Golden snapshot mismatch for {golden_name}.\n"
            f"  expected: {json.dumps(existing, ensure_ascii=False, indent=2)}\n"
            f"  got:      {json.dumps(snapshot, ensure_ascii=False, indent=2)}"
        )


# ---------------------------------------------------------------------------
# 2. _hybrid_retrieve — golden: doc IDs returned for fixed stubs
# ---------------------------------------------------------------------------


class TestHybridRetrieveGolden:
    """Golden characterization for _hybrid_retrieve output shape."""

    def _make_qdrant_stub(self, docs: list[dict]) -> MagicMock:
        """Qdrant stub that returns fixed docs from hybrid_search_rrf."""
        qdrant = MagicMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=docs)
        qdrant.query_points = AsyncMock(return_value=MagicMock(points=[]))
        return qdrant

    def _make_embeddings_stub(self) -> MagicMock:
        """Embeddings stub: fixed dense vector."""
        emb = MagicMock()
        emb.aembed_query = AsyncMock(return_value=[0.1] * 128)
        emb.aembed_hybrid_with_colbert = AsyncMock(
            return_value=([0.1] * 128, {"values": [1.0], "indices": [0]}, [[0.1] * 64])
        )
        return emb

    def _make_sparse_stub(self) -> MagicMock:
        sparse = MagicMock()
        sparse.aembed_query = AsyncMock(return_value={"values": [1.0], "indices": [0]})
        return sparse

    def _make_cache_stub(self) -> MagicMock:
        cache = MagicMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.store_search_results = AsyncMock(return_value=None)
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock(return_value=None)
        cache.get_bge_m3_query_bundle = AsyncMock(return_value=None)
        cache.store_bge_m3_query_bundle = AsyncMock(return_value=None)
        return cache

    @pytest.mark.asyncio
    async def test_golden_hybrid_retrieve_returns_docs(self) -> None:
        """Golden: _hybrid_retrieve with fixed qdrant stub returns expected doc IDs."""
        qdrant = self._make_qdrant_stub(_FIXTURE_CORPUS)
        cache = self._make_cache_stub()
        embeddings = self._make_embeddings_stub()
        sparse = self._make_sparse_stub()

        # Patch the qdrant retrieval internals to short-circuit to our stub docs
        with patch(
            "src.runtime.pipeline._cache_stage._retrieve_with_relaxation",
            AsyncMock(
                return_value=MagicMock(
                    results=_FIXTURE_CORPUS,
                    search_meta={},
                    colbert_search_used=False,
                    final_filters=None,
                    qdrant_search_attempts=1,
                    retrieval_relaxed_from_topic_filter=False,
                )
            ),
        ):
            result = await _hybrid_retrieve(
                _GOLDEN_QUERY,
                [0.1] * 128,  # pre-computed dense embedding
                cache=cache,
                sparse_embeddings=sparse,
                qdrant=qdrant,
                embeddings=embeddings,
                latency_stages={},
            )

        assert result["documents"] == _FIXTURE_CORPUS
        assert result["search_results_count"] == 3
        assert result["retrieval_backend_error"] is False

    @pytest.mark.asyncio
    async def test_golden_hybrid_retrieve_doc_ids(self) -> None:
        """Golden: source_ids from returned docs must match fixture corpus."""
        qdrant = self._make_qdrant_stub(_FIXTURE_CORPUS)
        cache = self._make_cache_stub()
        embeddings = self._make_embeddings_stub()
        sparse = self._make_sparse_stub()

        with patch(
            "src.runtime.pipeline._cache_stage._retrieve_with_relaxation",
            AsyncMock(
                return_value=MagicMock(
                    results=_FIXTURE_CORPUS,
                    search_meta={},
                    colbert_search_used=False,
                    final_filters=None,
                    qdrant_search_attempts=1,
                    retrieval_relaxed_from_topic_filter=False,
                )
            ),
        ):
            result = await _hybrid_retrieve(
                _GOLDEN_QUERY,
                [0.1] * 128,
                cache=cache,
                sparse_embeddings=sparse,
                qdrant=qdrant,
                embeddings=embeddings,
                latency_stages={},
            )

        returned_ids = [d["metadata"]["source_id"] for d in result["documents"]]
        expected_ids = ["doc_sunny_beach_studio", "doc_cleaning_service", "doc_legal_status"]
        assert returned_ids == expected_ids, (
            f"Golden hybrid_retrieve doc IDs mismatch.\n"
            f"  expected: {expected_ids}\n  got: {returned_ids}"
        )

    @pytest.mark.asyncio
    async def test_golden_hybrid_retrieve_snapshot(self) -> None:
        """Golden file snapshot for _hybrid_retrieve result shape."""
        qdrant = self._make_qdrant_stub(_FIXTURE_CORPUS)
        cache = self._make_cache_stub()
        embeddings = self._make_embeddings_stub()
        sparse = self._make_sparse_stub()

        with patch(
            "src.runtime.pipeline._cache_stage._retrieve_with_relaxation",
            AsyncMock(
                return_value=MagicMock(
                    results=_FIXTURE_CORPUS,
                    search_meta={},
                    colbert_search_used=False,
                    final_filters=None,
                    qdrant_search_attempts=1,
                    retrieval_relaxed_from_topic_filter=False,
                )
            ),
        ):
            result = await _hybrid_retrieve(
                _GOLDEN_QUERY,
                [0.1] * 128,
                cache=cache,
                sparse_embeddings=sparse,
                qdrant=qdrant,
                embeddings=embeddings,
                latency_stages={},
            )

        snapshot = {
            "search_results_count": result["search_results_count"],
            "retrieval_backend_error": result["retrieval_backend_error"],
            "search_cache_hit": result["search_cache_hit"],
            "rerank_applied": result["rerank_applied"],
            "doc_ids": [d["metadata"]["source_id"] for d in result["documents"]],
        }

        golden_name = "hybrid_retrieve.json"
        existing = _read_golden(golden_name)
        if not existing:
            _write_golden(golden_name, snapshot)
            return

        assert snapshot == existing, (
            f"Golden snapshot mismatch for {golden_name}.\n"
            f"  expected: {json.dumps(existing, ensure_ascii=False, indent=2)}\n"
            f"  got:      {json.dumps(snapshot, ensure_ascii=False, indent=2)}"
        )


# ---------------------------------------------------------------------------
# 3. generate_answer — golden: answer shape snapshot
# ---------------------------------------------------------------------------


def _fake_style_detector() -> MagicMock:
    detector = MagicMock()
    detector.detect.return_value = StyleInfo(
        style="balanced", difficulty="medium", reasoning="golden-test", word_count=5
    )
    return detector


def _base_dyn() -> dict:
    return {
        "ResponseStyleDetector": lambda: _fake_style_detector(),
        "detect_coverage_mode": lambda _q: CoverageDecision(False, None),
        "get_prompt_with_config": lambda name, **_kw: (f"sys:{name}", {"max_tokens": 300}),
        "get_prompt_with_object": lambda _n, **_kw: (None, None),
        "build_system_prompt_with_manager": lambda **_kw: "style_sys_golden",
        "get_token_limit": lambda _s, _d: 512,
        "PipelineMetrics": MagicMock(get=MagicMock(return_value=MagicMock(record=MagicMock()))),
    }


def _make_llm_mock(answer: str, model: str = "golden-llm-model") -> MagicMock:
    choice = SimpleNamespace(message=SimpleNamespace(content=answer))
    usage = SimpleNamespace(completion_tokens=20)
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = model
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=resp)
    return llm


def _make_config(llm: MagicMock, *, show_sources: bool = False) -> MagicMock:
    cfg = MagicMock()
    cfg.show_sources = show_sources
    cfg.response_style_enabled = False
    cfg.response_style_shadow_mode = False
    cfg.generate_max_tokens = 512
    cfg.domain = "real-estate"
    cfg.llm_temperature = 0.2
    cfg.llm_model = "golden-llm-model"
    cfg.get_reasoning_kwargs.return_value = {}
    cfg.create_llm.return_value = llm
    return cfg


class TestGenerateAnswerGolden:
    """Golden characterization for generate_answer output shape."""

    @pytest.mark.asyncio
    async def test_golden_answer_text_returned(self) -> None:
        """Golden: generate_answer must return the LLM answer text unchanged."""
        expected = (
            "Стоимость апартаментов — 115 000 EUR. Акт 16 выдан, правовой статус подтверждён."
        )
        llm = _make_llm_mock(expected)
        cfg = _make_config(llm)

        request = GenerationRequest(
            query=_GOLDEN_QUERY,
            documents=_FIXTURE_CORPUS,
            grounding_mode="normal",
            llm_call_count=0,
            config=cfg,
            extra_kwargs=_base_dyn(),
        )

        result = await generate_answer(request)

        assert result.response_text == expected, (
            f"Golden: expected answer text '{expected}', got '{result.response_text}'"
        )

    @pytest.mark.asyncio
    async def test_golden_grounded_true(self) -> None:
        """Golden: grounded must be True when LLM answers successfully."""
        llm = _make_llm_mock("Some answer with grounding.")
        cfg = _make_config(llm)

        request = GenerationRequest(
            query=_GOLDEN_QUERY,
            documents=_FIXTURE_CORPUS,
            grounding_mode="normal",
            llm_call_count=0,
            config=cfg,
            extra_kwargs=_base_dyn(),
        )

        result = await generate_answer(request)

        assert result.payload["grounded"] is True, (
            f"Golden: expected grounded=True, got {result.payload['grounded']}"
        )

    @pytest.mark.asyncio
    async def test_golden_llm_call_count_incremented(self) -> None:
        """Golden: llm_call_count must be incremented by 1 per successful call."""
        llm = _make_llm_mock("Answer.")
        cfg = _make_config(llm)

        request = GenerationRequest(
            query=_GOLDEN_QUERY,
            documents=_FIXTURE_CORPUS,
            grounding_mode="normal",
            llm_call_count=0,
            config=cfg,
            extra_kwargs=_base_dyn(),
        )

        result = await generate_answer(request)

        assert result.payload["llm_call_count"] == 1, (
            f"Golden: expected llm_call_count=1, got {result.payload['llm_call_count']}"
        )

    @pytest.mark.asyncio
    async def test_golden_safe_fallback_when_empty_docs_strict_mode(self) -> None:
        """Golden: strict mode + empty docs → safe_fallback_used=True, no LLM call."""
        llm = _make_llm_mock("should not be called")
        cfg = _make_config(llm, show_sources=True)

        request = GenerationRequest(
            query=_GOLDEN_QUERY,
            documents=[],  # empty docs → strict grounding not safe
            grounding_mode="strict",
            grade_confidence=0.05,
            llm_call_count=0,
            config=cfg,
            extra_kwargs=_base_dyn(),
        )

        result = await generate_answer(request)

        assert result.payload["safe_fallback_used"] is True, (
            "Golden: expected safe_fallback_used=True for strict mode + empty docs"
        )
        assert result.payload["grounded"] is False
        llm.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_golden_snapshot_answer_shape(self) -> None:
        """Golden file snapshot for generate_answer result shape.

        Captures the structural shape of the returned payload.
        A refactor that breaks field names, grounding flags, or call counting
        will produce a diff here.
        """
        expected = "Стоимость 115 000 EUR, акт 16 выдан."
        llm = _make_llm_mock(expected)
        cfg = _make_config(llm)

        request = GenerationRequest(
            query=_GOLDEN_QUERY,
            documents=[_DOC_SUNNY_BEACH, _DOC_LEGAL],
            grounding_mode="normal",
            llm_call_count=0,
            config=cfg,
            extra_kwargs=_base_dyn(),
        )

        result = await generate_answer(request)

        snapshot = {
            "response_text": result.response_text,
            "grounded": result.payload["grounded"],
            "safe_fallback_used": result.payload["safe_fallback_used"],
            "llm_call_count": result.payload["llm_call_count"],
            "llm_provider_model": result.payload["llm_provider_model"],
            "streaming_enabled": result.payload.get("streaming_enabled", False),
        }

        golden_name = "generate_answer.json"
        existing = _read_golden(golden_name)
        if not existing:
            _write_golden(golden_name, snapshot)
            return

        assert snapshot == existing, (
            f"Golden snapshot mismatch for {golden_name}.\n"
            f"  expected: {json.dumps(existing, ensure_ascii=False, indent=2)}\n"
            f"  got:      {json.dumps(snapshot, ensure_ascii=False, indent=2)}"
        )
