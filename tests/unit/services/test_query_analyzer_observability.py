# tests/unit/services/test_query_analyzer_observability.py
"""Unit tests for QueryAnalyzer Langfuse instrumentation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestQueryAnalyzerObservability:
    """Tests for QueryAnalyzer.analyze @observe decorator."""

    @pytest.fixture
    def analyzer(self):
        """Create QueryAnalyzer with mocked HTTP client."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="http://localhost:4000",
            model="gpt-4o-mini",
        )
        analyzer.client = MagicMock()
        return analyzer

    @pytest.mark.asyncio
    async def test_analyze_updates_generation(self, analyzer):
        """analyze should call update_current_generation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"filters": {"price": {"lt": 100000}}, "semantic_query": "квартиры"}'
                    }
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        }
        analyzer.client.post = AsyncMock(return_value=mock_response)

        with patch("telegram_bot.services.query_analyzer.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await analyzer.analyze("квартиры до 100000")

            assert mock_langfuse.update_current_generation.call_count == 2
            second_call = mock_langfuse.update_current_generation.call_args_list[1]
            assert "filters" in second_call.kwargs["output"]
