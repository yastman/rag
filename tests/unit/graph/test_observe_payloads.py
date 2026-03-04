"""Tests: heavy nodes disable @observe auto-capture, curated span has no heavy fields."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.runtime import Runtime


def _rt(**ctx) -> Runtime:
    return Runtime(context=ctx)


# ---------------------------------------------------------------------------
# Test 1: Heavy nodes use capture_input=False, capture_output=False
# ---------------------------------------------------------------------------


class TestHeavyNodesDisableAutoCapture:
    """Verify @observe(capture_input=False, capture_output=False) on heavy nodes."""

    @pytest.fixture(autouse=True)
    def _patch_observe(self):
        """Mock observe decorator before importing node modules.

        Replaces telegram_bot.observability.observe with a mock that records
        the kwargs passed to @observe(...) and returns the original function.
        """
        self.observe_calls: dict[str, dict] = {}
        original_modules: dict[str, object] = {}

        # Remove cached node modules so re-import picks up our mock
        node_modules = [
            "telegram_bot.graph.nodes.retrieve",
            "telegram_bot.graph.nodes.generate",
            "telegram_bot.graph.nodes.cache",
            "telegram_bot.graph.nodes.respond",
        ]
        for mod in node_modules:
            if mod in sys.modules:
                original_modules[mod] = sys.modules.pop(mod)

        def fake_observe(**kwargs):
            def decorator(func):
                self.observe_calls[kwargs.get("name", func.__name__)] = kwargs
                return func

            return decorator

        with patch("telegram_bot.observability.observe", side_effect=fake_observe):
            # Force re-import with our mocked observe
            for mod in node_modules:
                importlib.import_module(mod)
            yield

        # Restore original modules
        for mod in node_modules:
            sys.modules.pop(mod, None)
        for mod, original in original_modules.items():
            sys.modules[mod] = original  # type: ignore[assignment]

    @pytest.mark.parametrize(
        "node_name",
        [
            "node-retrieve",
            "node-generate",
            "node-cache-check",
            "node-cache-store",
            "node-respond",
        ],
    )
    def test_node_disables_auto_capture(self, node_name):
        kwargs = self.observe_calls.get(node_name, {})
        assert kwargs.get("capture_input") is False, f"{node_name} must set capture_input=False"
        assert kwargs.get("capture_output") is False, f"{node_name} must set capture_output=False"


# ---------------------------------------------------------------------------
# Test 2: Curated span payloads contain no heavy fields
# ---------------------------------------------------------------------------

# Forbidden keys — these must NEVER appear in update_current_span input/output
_FORBIDDEN_KEYS = {"documents", "query_embedding", "sparse_embedding", "state", "messages"}


def _extract_span_payloads(mock_lf_client: MagicMock) -> list[dict]:
    """Collect all input/output dicts from update_current_span calls."""
    payloads: list[dict] = []
    for c in mock_lf_client.update_current_span.call_args_list:
        kwargs = c.kwargs or {}
        if "input" in kwargs and isinstance(kwargs["input"], dict):
            payloads.append(kwargs["input"])
        if "output" in kwargs and isinstance(kwargs["output"], dict):
            payloads.append(kwargs["output"])
    return payloads


def _assert_no_forbidden_keys(payloads: list[dict], node_name: str) -> None:
    """Assert none of the payloads contain forbidden heavy keys."""
    for payload in payloads:
        for key in _FORBIDDEN_KEYS:
            assert key not in payload, (
                f"{node_name}: update_current_span must not contain '{key}', "
                f"found in payload keys: {list(payload.keys())}"
            )


class TestCuratedSpanPayloads:
    """Verify update_current_span calls contain only curated metadata."""

    async def test_retrieve_node_curated_payload(self):
        from telegram_bot.graph.nodes.retrieve import retrieve_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query text")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        docs = [
            {"id": "1", "text": "Doc content " * 100, "score": 0.9, "metadata": {}},
            {"id": "2", "text": "More content " * 100, "score": 0.7, "metadata": {}},
        ]
        ok_meta = {"backend_error": False, "error_type": None, "error_message": None}

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse = AsyncMock()
        sparse.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(docs, ok_meta))

        mock_lf = MagicMock()
        with patch("telegram_bot.graph.nodes.retrieve.get_client", return_value=mock_lf):
            await retrieve_node(state, _rt(cache=cache, sparse_embeddings=sparse, qdrant=qdrant))

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, (
            "retrieve_node must call update_current_span for input and output"
        )
        _assert_no_forbidden_keys(payloads, "node-retrieve")

        # Verify expected curated keys exist in input
        input_payload = payloads[0]
        assert "query_preview" in input_payload
        assert len(input_payload["query_preview"]) <= 120
        assert "query_hash" in input_payload
        assert len(input_payload["query_hash"]) == 8

    async def test_generate_node_curated_payload(self):
        from unittest.mock import patch as _patch

        from telegram_bot.graph.nodes.generate import generate_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["documents"] = [
            {"text": "Large doc " * 200, "score": 0.9, "metadata": {"title": "Test"}},
        ]

        mock_choice = MagicMock()
        mock_choice.message.content = "Answer."
        mock_response = MagicMock(choices=[mock_choice])
        mock_response.model = "gpt-4o-mini"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_config = MagicMock()
        mock_config.domain = "test"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = False
        mock_config.create_llm.return_value = mock_client

        mock_lf = MagicMock()
        with (
            _patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            _patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            await generate_node(state)

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, (
            "generate_node must call update_current_span for input and output"
        )
        _assert_no_forbidden_keys(payloads, "node-generate")

    async def test_cache_check_node_curated_payload(self):
        from telegram_bot.graph.nodes.cache import cache_check_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.1] * 16)
        cache.check_semantic = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()

        embeddings = AsyncMock()
        mock_lf = MagicMock()
        with patch("telegram_bot.graph.nodes.cache.get_client", return_value=mock_lf):
            await cache_check_node(state, _rt(cache=cache, embeddings=embeddings))

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, (
            "cache_check_node must call update_current_span for input and output"
        )
        _assert_no_forbidden_keys(payloads, "node-cache-check")

    async def test_cache_store_node_curated_payload(self):
        from telegram_bot.graph.nodes.cache import cache_store_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["response"] = "Answer"
        state["query_embedding"] = [0.2] * 16
        state["search_results_count"] = 5

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        mock_lf = MagicMock()
        with patch("telegram_bot.graph.nodes.cache.get_client", return_value=mock_lf):
            await cache_store_node(state, _rt(cache=cache))

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, (
            "cache_store_node must call update_current_span for input and output"
        )
        _assert_no_forbidden_keys(payloads, "node-cache-store")

    async def test_respond_node_curated_payload(self):
        from telegram_bot.graph.nodes.respond import respond_node

        state = {
            "response": "Краткий ответ",
            "response_sent": False,
            "message": None,
            "latency_stages": {},
            # Heavy keys should not leak via curated span payloads
            "documents": [{"text": "doc"}],
            "query_embedding": [0.1, 0.2],
            "messages": [{"role": "user", "content": "q"}],
        }

        mock_lf = MagicMock()
        with patch("telegram_bot.graph.nodes.respond.get_client", return_value=mock_lf):
            await respond_node(state)

        payloads = _extract_span_payloads(mock_lf)
        assert len(payloads) >= 2, "respond_node must call update_current_span for input/output"
        _assert_no_forbidden_keys(payloads, "node-respond")
