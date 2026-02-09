# tests/unit/services/test_query_analyzer_observability.py
"""Unit tests for QueryAnalyzer Langfuse observability (OpenAI SDK).

With the OpenAI SDK migration, Langfuse auto-tracing is handled by the
langfuse.openai drop-in replacement — no manual update_current_generation
calls needed. This test verifies the SDK client is properly configured.
"""

from openai import AsyncOpenAI

from telegram_bot.services.query_analyzer import QueryAnalyzer


class TestQueryAnalyzerObservability:
    """Tests for QueryAnalyzer Langfuse integration via OpenAI SDK."""

    def test_uses_openai_sdk_client(self):
        """QueryAnalyzer should use AsyncOpenAI (langfuse drop-in)."""
        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="http://localhost:4000",
            model="gpt-4o-mini",
        )
        assert isinstance(analyzer.client, AsyncOpenAI)
