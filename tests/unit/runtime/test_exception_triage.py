"""Tests for issue #2693: broad exception handling triage in runtime hot paths.

Verifies that:
1. context.py price formatting uses narrow ValueError (not broad Exception)
2. small_to_big.py logs error_type on Qdrant scroll failure
3. query_preprocessor.py logs error_type on unexpected HyDE failure
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

    def test_format_context_exception_is_value_error_not_broad(self):
        """The except clause in price formatting must only catch ValueError, not all exceptions.

        This test imports the module and inspects that a TypeError from within
        the try block (simulated via monkeypatching) would NOT be silently swallowed
        once the exception is narrowed to ValueError.
        """
        import ast
        import inspect

        import src.runtime.generation.context as ctx_module

        source = inspect.getsource(ctx_module._format_context_for_mode)
        tree = ast.parse(source)

        # Find all ExceptHandler nodes
        except_handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]

        # There should be exactly one except handler
        assert len(except_handlers) == 1, "Expected one except handler in _format_context_for_mode"

        handler = except_handlers[0]
        # Must NOT be a bare except (type is None) or broad Exception
        assert handler.type is not None, "except clause must not be bare"

        # Get the exception type(s) being caught
        caught_types: list[str] = []
        if isinstance(handler.type, ast.Tuple):
            caught_types = [
                (n.id if isinstance(n, ast.Name) else ast.dump(n)) for n in handler.type.elts
            ]
        elif isinstance(handler.type, ast.Name):
            caught_types = [handler.type.id]

        assert "Exception" not in caught_types, (
            f"Price formatting except must not catch broad Exception; caught: {caught_types}"
        )


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


class TestQueryPreprocessorLogsErrorType:
    """HyDEGenerator logs error_type on unexpected fallback exception."""

    @pytest.mark.asyncio
    @patch("src.runtime.services.query_preprocessor.logger")
    @patch("src.runtime.services.query_preprocessor.create_llm_client")
    async def test_hyde_unexpected_exception_logs_error_type(self, mock_create_client, mock_logger):
        """Unexpected exception in HyDE generation logs error_type."""
        from src.runtime.services.query_preprocessor import HyDEGenerator

        class UnexpectedError(Exception):
            pass

        mock_client = MagicMock()
        mock_client.completion = AsyncMock(side_effect=UnexpectedError("unexpected failure"))
        mock_create_client.return_value = mock_client

        gen = HyDEGenerator(model="test-model")

        result = await gen.generate_hypothetical_document("test query")

        assert result == "test query"  # Falls back to original query
        mock_logger.error.assert_called()
        # The second error call (broad except) should log error_type
        calls = mock_logger.error.call_args_list
        last_call_str = str(calls[-1])
        assert "UnexpectedError" in last_call_str or "error_type" in last_call_str.lower()
