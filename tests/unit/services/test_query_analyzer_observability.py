# tests/unit/services/test_query_analyzer_observability.py
"""Unit tests for QueryAnalyzer observability around the LiteLLM SDK router."""

from src.runtime.llm.router import LiteLLMChatClient
from telegram_bot.services.query_analyzer import QueryAnalyzer


class TestQueryAnalyzerObservability:
    """Tests for QueryAnalyzer Langfuse integration via the SDK router."""

    def test_uses_litellm_sdk_router_client(self):
        """QueryAnalyzer should route structured calls through LiteLLMChatClient."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="",
            model="gpt-4o-mini",
        )
        assert isinstance(analyzer.client, LiteLLMChatClient)
