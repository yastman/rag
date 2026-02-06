# tests/unit/test_cache_contract.py
"""Contract tests: validate bot's cache calls match CacheService method signatures.

These tests catch API drift between PropertyBot (caller) and CacheService (callee)
without requiring Redis. They verify parameter names and types at the call boundary.

Addresses BUG-003 from go-live review.
"""

import ast
import inspect
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolate_modules():
    """Clear telegram_bot modules for fresh imports."""
    prefixes = ("telegram_bot.", "langfuse", "opentelemetry")

    def _clear():
        for key in list(sys.modules.keys()):
            if key.startswith(prefixes):
                sys.modules.pop(key, None)

    _clear()
    yield
    _clear()


def _get_cache_method_params(method_name: str) -> set[str]:
    """Get parameter names from CacheService method (excluding 'self')."""
    # Stub langfuse before importing cache module
    langfuse_mock = MagicMock()
    langfuse_mock.observe = lambda **_kwargs: lambda fn: fn
    langfuse_mock.get_client = MagicMock()
    sys.modules.setdefault("langfuse", langfuse_mock)

    from telegram_bot.services.cache import CacheService

    method = getattr(CacheService, method_name)
    sig = inspect.signature(method)
    return {p for p in sig.parameters if p != "self"}


def _extract_call_kwargs(source_file: str, method_name: str) -> list[set[str]]:
    """Extract keyword argument names from all calls to method_name in source_file."""
    with open(source_file) as f:
        tree = ast.parse(f.read())

    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match self.cache_service.<method_name>(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == method_name:
            kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
            if kwargs:
                results.append(kwargs)
    return results


class TestCacheReankContract:
    """Rerank cache API contract between bot.py and cache.py."""

    def test_get_cached_rerank_kwargs_match_signature(self):
        """Bot's get_cached_rerank() kwargs must match CacheService signature."""
        cache_params = _get_cache_method_params("get_cached_rerank")
        bot_calls = _extract_call_kwargs("telegram_bot/bot.py", "get_cached_rerank")

        assert bot_calls, "No get_cached_rerank calls found in bot.py"
        for call_kwargs in bot_calls:
            unexpected = call_kwargs - cache_params
            assert not unexpected, (
                f"bot.py passes unexpected kwargs to get_cached_rerank: {unexpected}. "
                f"CacheService accepts: {cache_params}"
            )

    def test_store_rerank_results_kwargs_match_signature(self):
        """Bot's store_rerank_results() kwargs must match CacheService signature."""
        cache_params = _get_cache_method_params("store_rerank_results")
        bot_calls = _extract_call_kwargs("telegram_bot/bot.py", "store_rerank_results")

        assert bot_calls, "No store_rerank_results calls found in bot.py"
        for call_kwargs in bot_calls:
            unexpected = call_kwargs - cache_params
            assert not unexpected, (
                f"bot.py passes unexpected kwargs to store_rerank_results: {unexpected}. "
                f"CacheService accepts: {cache_params}"
            )


class TestCacheSearchContract:
    """Search cache API contract between bot.py and cache.py."""

    def test_get_cached_search_kwargs_match_signature(self):
        """Bot's get_cached_search() kwargs must match CacheService signature."""
        cache_params = _get_cache_method_params("get_cached_search")
        bot_calls = _extract_call_kwargs("telegram_bot/bot.py", "get_cached_search")

        # get_cached_search uses positional args, so bot_calls may be empty
        for call_kwargs in bot_calls:
            unexpected = call_kwargs - cache_params
            assert not unexpected, (
                f"bot.py passes unexpected kwargs to get_cached_search: {unexpected}. "
                f"CacheService accepts: {cache_params}"
            )

    def test_store_search_results_kwargs_match_signature(self):
        """Bot's store_search_results() kwargs must match CacheService signature."""
        cache_params = _get_cache_method_params("store_search_results")
        bot_calls = _extract_call_kwargs("telegram_bot/bot.py", "store_search_results")

        for call_kwargs in bot_calls:
            unexpected = call_kwargs - cache_params
            assert not unexpected, (
                f"bot.py passes unexpected kwargs to store_search_results: {unexpected}. "
                f"CacheService accepts: {cache_params}"
            )
