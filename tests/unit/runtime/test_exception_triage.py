"""Tests for issue #2693: broad exception handling triage in runtime hot paths.

Verifies that:
1. context.py price formatting keeps the ValueError scope narrow and
   propagates unexpected errors (#3406 replaced the AST source inspection
   with a direct TypeError propagation test)
2. small_to_big.py logs error_type on Qdrant scroll failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestContextPriceFormattingExceptionScope:
    """_format_context_for_mode narrows price formatting exception to ValueError."""

    def test_format_context_handles_valid_prices(self):
        """Normal int/float prices format without exception."""
        from src.runtime.generation.context import _format_context_for_mode

        docs = [
            {"text": "apt", "metadata": {"price": 150000}, "score": 0.9},
            {"text": "apt2", "metadata": {"price": 75000.5}, "score": 0.8},
        ]
        result = _format_context_for_mode(docs, sources_enabled=False)
        assert "150,000€" in result or "150000" in result  # formatted or fallback
        assert "apt" in result

    def test_format_context_price_string_fallback(self):
        """Non-numeric price falls through to string fallback path."""
        from src.runtime.generation.context import _format_context_for_mode

        docs = [{"text": "apt", "metadata": {"price": "по договору"}, "score": 0.9}]
        result = _format_context_for_mode(docs, sources_enabled=False)
        assert "по договору€" in result

    def test_format_context_propagates_type_error_from_price(self):
        """A TypeError from price formatting must propagate, not be swallowed (#3406).

        The except clause is narrowed to ValueError. A numeric price whose
        grouped formatting fails with TypeError (replacing a broad-Exception
        catch) must escape _format_context_for_mode instead of degrading into
        the string fallback path.
        """

        from src.runtime.generation.context import _format_context_for_mode

        class GroupFormatFailurePrice(float):
            """Float whose ',' grouped formatting fails with TypeError."""

            def __format__(self, spec: str) -> str:
                if "," in spec:
                    raise TypeError("grouped format unsupported")
                return str(float(self))

        docs = [
            {"text": "apt", "metadata": {"price": GroupFormatFailurePrice(150000)}, "score": 0.9}
        ]

        with pytest.raises(TypeError, match="grouped format unsupported"):
            _format_context_for_mode(docs, sources_enabled=False)


class TestSmallToBigLogsErrorType:
    """SmallToBigService._fetch_neighbors logs error_type on Qdrant failure."""

    @pytest.mark.asyncio
    @patch("src.runtime.services.small_to_big.logger")
    async def test_fetch_neighbors_logs_error_type_on_failure(self, mock_logger):
        """When Qdrant scroll fails, error_type appears in the log message."""
        from src.runtime.services.small_to_big import SmallToBigService

        mock_client = MagicMock()

        class CustomQdrantError(Exception):
            pass

        mock_client.scroll = AsyncMock(side_effect=CustomQdrantError("timeout"))
        service = SmallToBigService(mock_client, "test_collection")

        result = await service._fetch_neighbors("doc1", 5, window_before=1, window_after=1)

        assert result == []
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        # The log must include the error type name
        log_str = str(call_args)
        assert "CustomQdrantError" in log_str or "error_type" in log_str.lower()
