"""Graph path integration tests — verify all 5 routing paths through graph.ainvoke().

Tests build the real LangGraph StateGraph with mocked services,
invoke it with deterministic queries, and assert:
  1. Final state field values (which path was taken)
  2. Service call counts (which nodes executed)
  3. Negative assertions (which nodes were skipped)

No Docker, no network, no Langfuse required. All services mocked.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.graph import build_graph
from telegram_bot.graph.state import make_initial_state


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Shared helpers
***REMOVED*** ---------------------------------------------------------------------------


def _make_llm_completion(content: str) -> MagicMock:
    """Create a mock OpenAI ChatCompletion response."""
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


def _make_graph_mocks(
    *,
    cache_embedding: list[float] | None = None,
    cache_semantic: str | None = None,
    cache_search_results: list | None = None,
    cache_sparse: dict | None = None,
    qdrant_results: list[dict] | None = None,
    reranker_results: list[dict] | None = None,
    llm_response: str = "LLM answer",
) -> dict:
    """Build mock services for build_graph().

    Defaults represent a cache-miss happy path:
    - cache: all misses
    - embeddings: returns 1024-dim vector
    - sparse: returns indices/values dict
    - qdrant: returns 2 relevant docs (score > 0.3)
    - reranker: reorders docs (sets rerank_applied=True)
    - llm: returns llm_response
    - message: accepts answer() calls
    """
    ***REMOVED*** -- Cache --
    cache = MagicMock()
    cache.get_embedding = AsyncMock(return_value=cache_embedding)
    cache.store_embedding = AsyncMock()
    cache.check_semantic = AsyncMock(return_value=cache_semantic)
    cache.store_semantic = AsyncMock()
    cache.get_search_results = AsyncMock(return_value=cache_search_results)
    cache.store_search_results = AsyncMock()
    cache.get_sparse_embedding = AsyncMock(return_value=cache_sparse)
    cache.store_sparse_embedding = AsyncMock()
    cache.store_conversation_batch = AsyncMock()

    ***REMOVED*** -- Embeddings (dense) --
    embeddings = MagicMock()
    embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1024)

    ***REMOVED*** -- Sparse embeddings --
    sparse_embeddings = MagicMock()
    sparse_embeddings.aembed_query = AsyncMock(
        return_value={"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]}
    )

    ***REMOVED*** -- Qdrant --
    default_docs = [
        {
            "text": "Квартира в Несебр, 85000 евро",
            "score": 0.9,
            "id": "1",
            "metadata": {"title": "Квартира", "city": "Несебр", "price": 85000},
        },
        {
            "text": "Студия в Солнечный берег, 60000 евро",
            "score": 0.85,
            "id": "2",
            "metadata": {"title": "Студия", "city": "Солнечный берег", "price": 60000},
        },
    ]
    qdrant = MagicMock()
    qdrant.hybrid_search_rrf = AsyncMock(
        return_value=qdrant_results if qdrant_results is not None else default_docs
    )

    ***REMOVED*** -- Reranker (ColBERT) --
    reranker = MagicMock()
    default_rerank = [{"index": 0, "score": 0.95}, {"index": 1, "score": 0.80}]
    reranker.rerank = AsyncMock(
        return_value=reranker_results if reranker_results is not None else default_rerank
    )

    ***REMOVED*** -- LLM (OpenAI SDK pattern) --
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=_make_llm_completion(llm_response))

    ***REMOVED*** -- Telegram message --
    message = MagicMock()
    message.answer = AsyncMock()
    message.chat = MagicMock(id=12345)

    return {
        "cache": cache,
        "embeddings": embeddings,
        "sparse_embeddings": sparse_embeddings,
        "qdrant": qdrant,
        "reranker": reranker,
        "llm": llm,
        "message": message,
    }


def _make_mock_graph_config(llm_mock: MagicMock) -> MagicMock:
    """Create a mock GraphConfig with all required typed fields."""
    gc = MagicMock()
    gc.domain = "недвижимость"
    gc.llm_model = "test-model"
    gc.llm_temperature = 0.7
    gc.llm_max_tokens = 4096
    gc.generate_max_tokens = 2048
    gc.rewrite_model = "test-model"
    gc.rewrite_max_tokens = 64
    gc.skip_rerank_threshold = 0.95
    gc.streaming_enabled = False
    gc.create_llm.return_value = llm_mock
    return gc


@contextmanager
def _patch_graph_configs(mock_gc: MagicMock):
    """Patch both config entry points used by generate_node and rewrite_node."""
    with (
        patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_gc),
        patch("telegram_bot.graph.config.GraphConfig.from_env", return_value=mock_gc),
    ):
        yield


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Path 1: classify(CHITCHAT) → respond → END
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_path_chitchat_early_exit():
    """Chitchat query skips cache/retrieve/generate, goes straight to respond."""
    mocks = _make_graph_mocks()
    mock_gc = _make_mock_graph_config(mocks["llm"])

    with _patch_graph_configs(mock_gc):
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
        )

    state = make_initial_state(user_id=1, session_id="test-path1", query="Привет!")

    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)

    ***REMOVED*** State assertions
    assert result["query_type"] == "CHITCHAT"
    assert result["response"]  ***REMOVED*** non-empty canned response
    assert result["cache_hit"] is False
    assert result["documents"] == []

    ***REMOVED*** Skipped nodes: no cache, no search, no LLM
    mocks["cache"].get_embedding.assert_not_awaited()
    mocks["cache"].check_semantic.assert_not_awaited()
    mocks["qdrant"].hybrid_search_rrf.assert_not_awaited()
    mocks["llm"].chat.completions.create.assert_not_awaited()
    mocks["reranker"].rerank.assert_not_awaited()

    ***REMOVED*** respond_node sent the message
    mocks["message"].answer.assert_awaited_once()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Path 2: classify(GENERAL) → cache_check(HIT) → respond → END
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_path_cache_hit():
    """Cached response skips retrieve/grade/rerank/generate."""
    cached_text = "Вот кэшированный ответ про квартиры."
    mocks = _make_graph_mocks(
        cache_embedding=[0.1] * 1024,  ***REMOVED*** embedding found in cache
        cache_semantic=cached_text,  ***REMOVED*** semantic cache hit
    )
    mock_gc = _make_mock_graph_config(mocks["llm"])

    with _patch_graph_configs(mock_gc):
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
        )

    ***REMOVED*** Use a query that classifies as GENERAL (goes to cache_check)
    state = make_initial_state(
        user_id=2, session_id="test-path2", query="уютная квартира с видом на море"
    )

    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)

    ***REMOVED*** State assertions
    assert result["cache_hit"] is True
    assert result["cached_response"] == cached_text
    assert result["response"] == cached_text
    assert result["documents"] == []

    ***REMOVED*** Skipped nodes: no search, no LLM
    mocks["qdrant"].hybrid_search_rrf.assert_not_awaited()
    mocks["llm"].chat.completions.create.assert_not_awaited()
    mocks["reranker"].rerank.assert_not_awaited()

    ***REMOVED*** respond_node sent the cached response
    mocks["message"].answer.assert_awaited_once()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Path 3: classify → cache_check(MISS) → retrieve → grade(relevant)
***REMOVED***        → rerank → generate → cache_store → respond → END
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_path_happy_retrieve_rerank_generate():
    """Full RAG path: cache miss, relevant docs, rerank, generate."""
    mocks = _make_graph_mocks(llm_response="Найдено 2 варианта квартир.")
    mock_gc = _make_mock_graph_config(mocks["llm"])

    with _patch_graph_configs(mock_gc):
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
        )

    state = make_initial_state(
        user_id=3, session_id="test-path3", query="уютная квартира с видом на море"
    )

    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)

    ***REMOVED*** State assertions
    assert result["cache_hit"] is False
    assert result["documents_relevant"] is True
    assert result["rerank_applied"] is True
    assert result["search_results_count"] == 2
    assert result["response"] == "Найдено 2 варианта квартир."
    assert result["rewrite_count"] == 0

    ***REMOVED*** Service call counts
    mocks["qdrant"].hybrid_search_rrf.assert_awaited_once()
    mocks["reranker"].rerank.assert_awaited_once()
    mocks["llm"].chat.completions.create.assert_awaited_once()  ***REMOVED*** generate only

    ***REMOVED*** Cache stored
    mocks["cache"].store_semantic.assert_awaited_once()
    mocks["cache"].store_conversation_batch.assert_awaited_once()


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Path 4: classify → cache_check(MISS) → retrieve → grade(irrelevant)
***REMOVED***        → rewrite → retrieve → grade(relevant) → rerank → generate → ...
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_path_rewrite_loop_then_success():
    """Irrelevant docs trigger rewrite, second retrieve finds relevant docs."""
    irrelevant_docs = [
        {"text": "Нерелевантный текст", "score": 0.1, "id": "x1", "metadata": {}},
    ]
    relevant_docs = [
        {
            "text": "Квартира в Несебр, 85000 евро",
            "score": 0.9,
            "id": "1",
            "metadata": {"title": "Квартира", "city": "Несебр", "price": 85000},
        },
    ]

    mocks = _make_graph_mocks()

    ***REMOVED*** Qdrant: 1st call → irrelevant, 2nd call → relevant
    mocks["qdrant"].hybrid_search_rrf = AsyncMock(side_effect=[irrelevant_docs, relevant_docs])

    ***REMOVED*** LLM: 1st call → rewrite query, 2nd call → generate answer
    rewrite_completion = _make_llm_completion("квартира Несебр недорого")
    generate_completion = _make_llm_completion("Найдена квартира после переформулировки.")
    mocks["llm"].chat.completions.create = AsyncMock(
        side_effect=[rewrite_completion, generate_completion]
    )

    ***REMOVED*** Reranker returns result for single relevant doc
    mocks["reranker"].rerank = AsyncMock(return_value=[{"index": 0, "score": 0.95}])

    mock_gc = _make_mock_graph_config(mocks["llm"])

    with _patch_graph_configs(mock_gc):
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
        )

    state = make_initial_state(
        user_id=4, session_id="test-path4", query="уютная квартира с видом на море"
    )

    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)

    ***REMOVED*** State assertions
    assert result["rewrite_count"] == 1
    assert result["documents_relevant"] is True
    assert result["response"] == "Найдена квартира после переформулировки."

    ***REMOVED*** Service call counts
    assert mocks["qdrant"].hybrid_search_rrf.await_count == 2  ***REMOVED*** retrieve twice
    assert mocks["llm"].chat.completions.create.await_count == 2  ***REMOVED*** rewrite + generate
    mocks["reranker"].rerank.assert_awaited_once()  ***REMOVED*** rerank on 2nd pass


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Path 5: classify → cache_check(MISS) → retrieve → grade(irrelevant)
***REMOVED***        → generate (rewrite_count >= 2) → cache_store → respond → END
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_path_rewrite_exhausted_fallback():
    """When rewrite_count >= 2, skip rewrite and go straight to generate."""
    irrelevant_docs = [
        {"text": "Не очень релевантный текст", "score": 0.15, "id": "z1", "metadata": {}},
    ]
    mocks = _make_graph_mocks(
        qdrant_results=irrelevant_docs,
        llm_response="К сожалению, точных совпадений не найдено.",
    )
    mock_gc = _make_mock_graph_config(mocks["llm"])

    with _patch_graph_configs(mock_gc):
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],  ***REMOVED*** real mock to detect incorrect routing
            llm=mocks["llm"],
            message=mocks["message"],
        )

    ***REMOVED*** Pre-set rewrite_count=2 to simulate exhausted retries
    state = make_initial_state(
        user_id=5, session_id="test-path5", query="уютная квартира с видом на море"
    )
    state["rewrite_count"] = 2

    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)

    ***REMOVED*** State assertions
    assert result["rewrite_count"] == 2  ***REMOVED*** not incremented — rewrite node not entered
    assert result["documents_relevant"] is False
    assert result["response"] == "К сожалению, точных совпадений не найдено."

    ***REMOVED*** Service call counts
    mocks["qdrant"].hybrid_search_rrf.assert_awaited_once()
    mocks["llm"].chat.completions.create.assert_awaited_once()  ***REMOVED*** generate only
    mocks["reranker"].rerank.assert_not_awaited()  ***REMOVED*** rerank node must be skipped


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Path 6: classify → cache_check(MISS) → retrieve → grade(irrelevant)
***REMOVED***        → generate (rewrite_effective=False) → cache_store → respond → END
***REMOVED*** ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_path_rewrite_ineffective_fallback():
    """When rewrite_effective=False (even with retries left), skip rewrite → generate."""
    irrelevant_docs = [
        {"text": "Не очень релевантный текст", "score": 0.15, "id": "z1", "metadata": {}},
    ]
    mocks = _make_graph_mocks(
        qdrant_results=irrelevant_docs,
        llm_response="К сожалению, ничего подходящего не найдено.",
    )
    mock_gc = _make_mock_graph_config(mocks["llm"])

    with _patch_graph_configs(mock_gc):
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
        )

    ***REMOVED*** rewrite_count=1 (< 2, retries left) but rewrite_effective=False
    state = make_initial_state(
        user_id=6, session_id="test-path6", query="уютная квартира с видом на море"
    )
    state["rewrite_count"] = 1
    state["rewrite_effective"] = False

    with _patch_graph_configs(mock_gc):
        result = await graph.ainvoke(state)

    ***REMOVED*** State assertions
    assert result["rewrite_count"] == 1  ***REMOVED*** rewrite node not entered
    assert result["documents_relevant"] is False
    assert result["response"] == "К сожалению, ничего подходящего не найдено."

    ***REMOVED*** Service call counts
    mocks["qdrant"].hybrid_search_rrf.assert_awaited_once()
    mocks["llm"].chat.completions.create.assert_awaited_once()  ***REMOVED*** generate only
    mocks["reranker"].rerank.assert_not_awaited()  ***REMOVED*** rerank skipped
