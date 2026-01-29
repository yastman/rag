# tests/unit/services/test_query_router_observability.py
"""Unit tests for QueryRouter Langfuse instrumentation."""

from unittest.mock import MagicMock, patch


class TestQueryRouterObservability:
    """Tests for classify_query @observe decorator."""

    def test_classify_query_updates_span(self):
        """classify_query should call update_current_span."""
        with patch("telegram_bot.services.query_router.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            from telegram_bot.services.query_router import QueryType, classify_query

            result = classify_query("Привет!")

            assert result == QueryType.CHITCHAT
            mock_langfuse.update_current_span.assert_called_once()
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["type"] == "chitchat"

    def test_classify_complex_query(self):
        """Complex queries should be tracked with type."""
        with patch("telegram_bot.services.query_router.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            from telegram_bot.services.query_router import QueryType, classify_query

            result = classify_query("квартиры до 100000 евро с двумя спальнями")

            assert result == QueryType.COMPLEX
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["type"] == "complex"
