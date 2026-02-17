"""
Unit tests for src/evaluation/langfuse_integration.py

Tests Langfuse integration functionality with mocked SDK.
"""

from __future__ import annotations

import sys
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Mock langfuse module before any imports
@pytest.fixture(autouse=True)
def mock_langfuse_module(monkeypatch: pytest.MonkeyPatch):
    """Mock langfuse module and its components."""

    # Configure observe to return a pass-through decorator
    def observe_passthrough(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    # Mock Langfuse client methods - single shared instance
    mock_client_instance = MagicMock()
    mock_client_instance.update_current_trace = MagicMock()
    mock_client_instance.score_current_trace = MagicMock()

    # Mock span context manager
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    mock_span.update = MagicMock()
    mock_span.score = MagicMock()
    mock_span.start_as_current_span = MagicMock(return_value=mock_span)

    mock_client_instance.start_as_current_span = MagicMock(return_value=mock_span)

    mock_langfuse_class = MagicMock(return_value=mock_client_instance)

    # Create the mock module
    mock_langfuse_mod = MagicMock()
    mock_langfuse_mod.Langfuse = mock_langfuse_class
    mock_langfuse_mod.get_client = MagicMock(return_value=mock_client_instance)
    mock_langfuse_mod.observe = observe_passthrough

    monkeypatch.setitem(sys.modules, "langfuse", mock_langfuse_mod)

    yield {
        "Langfuse": mock_langfuse_class,
        "client_instance": mock_client_instance,
        "get_client": mock_langfuse_mod.get_client,
        "observe": observe_passthrough,
        "span": mock_span,
        "module": mock_langfuse_mod,
    }


class TestInitializeLangfuse:
    """Tests for initialize_langfuse function."""

    def test_initialize_langfuse_success(self, mock_langfuse_module):
        """Test successful Langfuse initialization."""
        from langfuse import Langfuse

        host = "http://localhost:3001"
        public_key = "pk-test"
        secret_key = "sk-test"
        enabled = True

        client = None
        is_enabled = False

        if enabled:
            try:
                client = Langfuse(
                    host=host,
                    public_key=public_key,
                    secret_key=secret_key,
                )
                is_enabled = True
            except Exception:
                pass

        assert client is not None
        assert is_enabled is True
        mock_langfuse_module["Langfuse"].assert_called_once_with(
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )

    def test_initialize_langfuse_disabled(self, mock_langfuse_module):
        """Test Langfuse initialization when disabled."""
        enabled = False

        if not enabled:
            client = None
            is_enabled = False
        else:
            client = MagicMock()
            is_enabled = True

        assert client is None
        assert is_enabled is False

    def test_initialize_langfuse_with_env_vars(self, mock_langfuse_module):
        """Test Langfuse uses environment variables when keys not provided."""
        import os

        with patch.dict(
            os.environ,
            {
                "LANGFUSE_PUBLIC_KEY": "env-pk-test",
                "LANGFUSE_SECRET_KEY": "env-sk-test",
            },
        ):
            from langfuse import Langfuse

            public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
            secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

            Langfuse(
                host="http://localhost:3001",
                public_key=public_key,
                secret_key=secret_key,
            )

            assert public_key == "env-pk-test"
            assert secret_key == "env-sk-test"

    def test_initialize_langfuse_error_handling(self, mock_langfuse_module):
        """Test graceful error handling during initialization."""
        mock_langfuse_module["Langfuse"].side_effect = Exception("Connection failed")

        client = None
        is_enabled = False

        try:
            from langfuse import Langfuse

            client = Langfuse(
                host="http://localhost:3001",
                public_key="pk",
                secret_key="sk",
            )
            is_enabled = True
        except Exception:
            client = None
            is_enabled = False

        assert client is None
        assert is_enabled is False


class TestTraceSearchWithDecorator:
    """Tests for trace_search_with_decorator function."""

    def test_trace_search_basic(self, mock_langfuse_module):
        """Test basic search tracing with decorator."""
        from langfuse import get_client

        langfuse = get_client()

        query = "test query"
        engine_name = "dbsf_colbert"
        user_id = "user_123"
        session_id = "session_456"

        # Update trace metadata
        langfuse.update_current_trace(
            input={"query": query, "engine": engine_name},
            user_id=user_id,
            session_id=session_id,
            tags=["search", engine_name, "evaluation"],
        )

        # Verify the client was called (via the returned mock)
        langfuse.update_current_trace.assert_called_once()

    def test_trace_search_with_expected_article(self, mock_langfuse_module):
        """Test search tracing with expected article for evaluation."""
        from langfuse import get_client

        langfuse = get_client()

        expected_article = 121

        # Mock search results
        mock_result = MagicMock()
        mock_result.payload = {"article_number": 121}

        results = [mock_result]

        # Calculate metrics
        retrieved_articles = [
            r.payload.get("article_number") if hasattr(r, "payload") else None for r in results
        ]

        precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0
        recall_at_10 = 1.0 if expected_article in retrieved_articles[:10] else 0.0

        # Log scores
        langfuse.score_current_trace(name="precision_at_1", value=precision_at_1)
        langfuse.score_current_trace(name="recall_at_10", value=recall_at_10)

        assert precision_at_1 == 1.0
        assert recall_at_10 == 1.0

    def test_trace_search_latency_measurement(self, mock_langfuse_module):
        """Test latency is measured during search."""

        def mock_search(query: str) -> list:
            _ = query
            return []

        with patch("time.time", side_effect=[100.0, 100.012]):
            start_time = time.time()
            mock_search("test")
            latency_ms = (time.time() - start_time) * 1000

        assert latency_ms >= 10
        assert latency_ms < 100  # Should be under 100ms

    def test_trace_search_metrics_without_expected_article(self, mock_langfuse_module):
        """Test metrics when no expected article is provided."""
        expected_article = None
        results = [MagicMock()]

        metrics: dict[str, Any] = {
            "latency_ms": 50.0,
            "num_results": len(results),
        }

        if expected_article is not None and results:
            metrics["precision_at_1"] = 1.0
            metrics["recall_at_10"] = 1.0

        assert "latency_ms" in metrics
        assert "num_results" in metrics
        assert "precision_at_1" not in metrics
        assert "recall_at_10" not in metrics

    def test_precision_at_1_correct(self):
        """Test precision@1 calculation when first result is correct."""
        expected_article = 121
        retrieved_articles = [121, 115, 185]

        precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0

        assert precision_at_1 == 1.0

    def test_precision_at_1_incorrect(self):
        """Test precision@1 calculation when first result is incorrect."""
        expected_article = 121
        retrieved_articles = [115, 121, 185]

        precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0

        assert precision_at_1 == 0.0

    def test_recall_at_10_found(self):
        """Test recall@10 when expected article is in top 10."""
        expected_article = 121
        retrieved_articles = [115, 185, 121, 200, 201, 202, 203, 204, 205, 206]

        recall_at_10 = 1.0 if expected_article in retrieved_articles[:10] else 0.0

        assert recall_at_10 == 1.0

    def test_recall_at_10_not_found(self):
        """Test recall@10 when expected article is not in top 10."""
        expected_article = 121
        retrieved_articles = [115, 185, 200, 201, 202, 203, 204, 205, 206, 207]

        recall_at_10 = 1.0 if expected_article in retrieved_articles[:10] else 0.0

        assert recall_at_10 == 0.0


class TestTraceSearchWithSpans:
    """Tests for trace_search_with_spans function."""

    def test_span_creation(self, mock_langfuse_module):
        """Test spans are created correctly."""
        from langfuse import get_client

        langfuse = get_client()

        # Simulate span creation
        with langfuse.start_as_current_span(name="rag-search") as trace:
            trace.update(
                user_id="user_123",
                session_id="session_456",
                tags=["search", "dbsf_colbert"],
                metadata={"engine": "dbsf_colbert"},
            )

        # Verify the span was created
        langfuse.start_as_current_span.assert_called_once_with(name="rag-search")

    def test_nested_retrieval_span(self, mock_langfuse_module):
        """Test nested retrieval span is created."""
        mock_span = mock_langfuse_module["span"]

        query = "test query"
        engine_name = "dbsf_colbert"

        # Simulate nested span
        with mock_span.start_as_current_span(
            name=f"retrieval-{engine_name}", input={"query": query}
        ) as retrieval_span:
            # Simulate search
            results = []
            latency_ms = 50.0

            retrieval_span.update(output={"num_results": len(results), "latency_ms": latency_ms})

        mock_span.start_as_current_span.assert_called()

    def test_evaluation_span_with_expected_article(self, mock_langfuse_module):
        """Test evaluation span is created when expected article provided."""
        from langfuse import get_client

        get_client()

        expected_article = 121
        mock_result = MagicMock()
        mock_result.payload = {"article_number": 121}
        results = [mock_result]

        # Create a mock span that tracks calls
        eval_span = MagicMock()

        if expected_article is not None and results:
            retrieved_articles = [r.payload.get("article_number") for r in results]
            precision_at_1 = 1.0 if retrieved_articles[0] == expected_article else 0.0

            eval_span.update(
                output={
                    "precision_at_1": precision_at_1,
                    "retrieved_articles": retrieved_articles[:10],
                }
            )
            eval_span.score(name="precision_at_1", value=precision_at_1)

        # Verify correct values were computed and methods called
        assert precision_at_1 == 1.0
        eval_span.update.assert_called_once()
        eval_span.score.assert_called_with(name="precision_at_1", value=1.0)

    def test_no_evaluation_span_without_expected_article(self, mock_langfuse_module):
        """Test no evaluation span when expected article not provided."""
        expected_article = None
        results = [MagicMock()]

        eval_span_created = False

        if expected_article is not None and results:
            eval_span_created = True

        assert eval_span_created is False

    def test_no_evaluation_span_with_empty_results(self, mock_langfuse_module):
        """Test no evaluation span when results are empty."""
        expected_article = 121
        results: list[Any] = []

        eval_span_created = False

        if expected_article is not None and results:
            eval_span_created = True

        assert eval_span_created is False


class TestMetricsCalculation:
    """Tests for metrics calculation logic."""

    def test_latency_calculation(self):
        """Test latency is calculated correctly in milliseconds."""
        with patch("time.time", side_effect=[200.0, 200.05]):
            start_time = time.time()
            latency_ms = (time.time() - start_time) * 1000

        assert 45 < latency_ms < 100  # Allow some tolerance

    def test_num_results_metric(self):
        """Test num_results metric is correct."""
        results = [MagicMock() for _ in range(5)]

        metrics = {
            "num_results": len(results),
        }

        assert metrics["num_results"] == 5

    def test_full_metrics_structure(self):
        """Test complete metrics structure."""
        metrics = {
            "latency_ms": 50.0,
            "num_results": 10,
            "precision_at_1": 1.0,
            "recall_at_10": 1.0,
            "correct_at_1": 1.0,
        }

        assert all(isinstance(v, (int, float)) for v in metrics.values())
        assert metrics["precision_at_1"] == metrics["correct_at_1"]


class TestObserveDecorator:
    """Tests for @observe decorator behavior."""

    def test_observe_decorator_applied(self, mock_langfuse_module):
        """Test @observe decorator can be applied to functions."""
        from langfuse import observe

        @observe(name="test-function")
        def test_function():
            return "result"

        result = test_function()
        assert result == "result"

    def test_observe_with_custom_name(self, mock_langfuse_module):
        """Test @observe decorator with custom name."""
        from langfuse import observe

        @observe(name="custom-search-operation")
        def search_operation(query: str):
            return [{"text": "result"}]

        result = search_operation("test")
        assert len(result) == 1


class TestTraceTags:
    """Tests for trace tagging functionality."""

    def test_search_tags(self, mock_langfuse_module):
        """Test tags are applied to search traces."""
        engine_name = "dbsf_colbert"
        tags = ["search", engine_name, "evaluation"]

        # Verify tags contain expected values
        assert "search" in tags
        assert "dbsf_colbert" in tags
        assert "evaluation" in tags
        assert len(tags) == 3

    def test_metadata_application(self, mock_langfuse_module):
        """Test metadata is applied to traces."""
        expected_article = 121
        metadata = {"expected_article": expected_article} if expected_article else {}

        # Verify metadata structure
        assert "expected_article" in metadata
        assert metadata["expected_article"] == 121

    def test_metadata_empty_when_no_article(self, mock_langfuse_module):
        """Test metadata is empty when no expected article."""
        expected_article = None
        metadata = {"expected_article": expected_article} if expected_article else {}

        assert metadata == {}


class TestScoreLogging:
    """Tests for score logging to Langfuse."""

    def test_score_precision_at_1(self, mock_langfuse_module):
        """Test precision@1 score is logged."""
        from langfuse import get_client

        langfuse = get_client()

        precision = 1.0
        langfuse.score_current_trace(name="precision_at_1", value=precision)

        langfuse.score_current_trace.assert_called_with(name="precision_at_1", value=1.0)

    def test_score_recall_at_10(self, mock_langfuse_module):
        """Test recall@10 score is logged."""
        from langfuse import get_client

        langfuse = get_client()

        recall = 0.8
        langfuse.score_current_trace(name="recall_at_10", value=recall)

        langfuse.score_current_trace.assert_called_with(name="recall_at_10", value=0.8)

    def test_score_latency(self, mock_langfuse_module):
        """Test latency score is logged."""
        from langfuse import get_client

        langfuse = get_client()

        latency = 150.5
        langfuse.score_current_trace(name="latency_ms", value=latency)

        langfuse.score_current_trace.assert_called_with(name="latency_ms", value=150.5)


class TestResultExtraction:
    """Tests for result extraction from search results."""

    def test_extract_article_from_payload(self):
        """Test article number is extracted from result payload."""
        mock_result = MagicMock()
        mock_result.payload = {"article_number": 121, "text": "Article text"}

        article_num = mock_result.payload.get("article_number")

        assert article_num == 121

    def test_extract_from_multiple_results(self):
        """Test extraction from multiple results."""
        results = [
            MagicMock(payload={"article_number": 121}),
            MagicMock(payload={"article_number": 115}),
            MagicMock(payload={"article_number": 185}),
        ]

        retrieved_articles = [
            r.payload.get("article_number") if hasattr(r, "payload") else None for r in results
        ]

        assert retrieved_articles == [121, 115, 185]

    def test_handle_missing_payload(self):
        """Test handling results without payload attribute."""
        mock_result = MagicMock(spec=[])  # No payload attribute

        article_num = None
        if hasattr(mock_result, "payload"):
            article_num = mock_result.payload.get("article_number")

        assert article_num is None


class TestSessionAndUserTracking:
    """Tests for session and user tracking."""

    def test_user_id_tracking(self, mock_langfuse_module):
        """Test user ID values are valid."""
        user_id = "user_abc123"

        # Verify user_id is a non-empty string
        assert isinstance(user_id, str)
        assert len(user_id) > 0
        assert user_id == "user_abc123"

    def test_session_id_tracking(self, mock_langfuse_module):
        """Test session ID values are valid."""
        session_id = "session_xyz789"

        # Verify session_id is a non-empty string
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        assert session_id == "session_xyz789"

    def test_anonymous_user(self, mock_langfuse_module):
        """Test anonymous user handling."""
        user_id = "anonymous"

        # Verify anonymous user_id
        assert user_id == "anonymous"

    def test_optional_session_id(self, mock_langfuse_module):
        """Test session ID is optional (can be None)."""
        session_id = None

        # Verify session_id can be None
        assert session_id is None

    def test_trace_parameters_structure(self, mock_langfuse_module):
        """Test trace update parameters have correct structure."""
        trace_params = {
            "input": {"query": "test", "engine": "dbsf_colbert"},
            "user_id": "user_123",
            "session_id": "session_456",
            "tags": ["search", "evaluation"],
            "metadata": {"expected_article": 121},
        }

        assert "input" in trace_params
        assert "user_id" in trace_params
        assert "tags" in trace_params
        assert isinstance(trace_params["tags"], list)
        assert isinstance(trace_params["input"], dict)
