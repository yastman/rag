"""Tests for the semantic-cache vectorizer module.

The custom BgeM3CacheVectorizer subclass was replaced by the official RedisVL
CustomVectorizer factory in #3389. Behavior-level characterization lives in
tests/unit/services/test_bge_m3_cache_vectorizer.py; this module pins the
import surface.
"""

import pytest


def test_vectorizers_module_importable() -> None:
    """Active vectorizer factory is importable without error.

    #3365: the module imports redisvl (optional ``redis`` extra), so the lean
    base+dev lane skips this pin; redis-enabled lanes run it for real.
    """
    pytest.importorskip("redisvl")
    from src.services.vectorizers import create_bge_m3_cache_vectorizer

    assert create_bge_m3_cache_vectorizer is not None
