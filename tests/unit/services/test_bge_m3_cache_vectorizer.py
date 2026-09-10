"""Characterization tests for the semantic-cache vectorizer (#3389).

Pins the contract the RedisVL SemanticCache depends on, independent of whether
it is provided by the historical ``BgeM3CacheVectorizer`` subclass or by the
official RedisVL ``CustomVectorizer``:

- 1024 dims / float32 dtype — the index schema inputs;
- async one/batch embedding delegates to ``BGEM3Client.encode_dense`` exactly
  once per call (one HTTP request per embed operation);
- the BGE client is created lazily and reused (no duplicate clients);
- construction performs no BGE calls — the vectorizer is used for index
  creation, and callers pass ``vector=`` explicitly.

Known intentional delta introduced with the #3389 CustomVectorizer refactor
(documented, accepted): the sync ``embed``/``embed_many`` surface changes from
``NotImplementedError`` to a local zero-vector probe that never contacts BGE
(RedisVL's ``CustomVectorizer`` construction validates dims via the sync
callable). Production never calls the sync surface: ``check_semantic`` /
``store_semantic`` always pass ``vector=``.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


BGE_DENSE_DIMS = 1024


def _dense_result(vectors: list[list[float]]) -> SimpleNamespace:
    """Shape-compatible stand-in for BGEM3Client DenseResult."""
    return SimpleNamespace(vectors=vectors)


def _make_vectorizer() -> Any:
    """Build the vectorizer under test.

    Single construction point so the pre/post-refactor parity run asserts the
    identical behavior list against both implementations.

    #3365: the module under test imports redisvl, which lives in the optional
    ``redis`` extra — skip this characterization in the lean base+dev lane;
    it runs wherever the redis extra is installed.
    """
    pytest.importorskip("redisvl")
    from src.services.vectorizers import create_bge_m3_cache_vectorizer

    return create_bge_m3_cache_vectorizer(base_url="http://bge-m3:8000")


def _patched_bge(
    vectors: list[list[float]],
) -> tuple[MagicMock, MagicMock, Any]:
    """Patch BGEM3Client at its lazy import site.

    Returns ``(class_mock, instance, patcher)`` — use the patcher as a
    context manager around the vectorizer calls under test.
    """
    instance = MagicMock()
    instance.encode_dense = AsyncMock(return_value=_dense_result(vectors))
    class_mock = MagicMock(return_value=instance)
    return class_mock, instance, patch("src.services.bge_m3_client.BGEM3Client", class_mock)  # type: ignore[return-value]


class TestSemanticCacheVectorizerContract:
    """Contract the semantic cache index and fallback embedding path rely on."""

    def test_dims_and_dtype_are_index_schema_inputs(self) -> None:
        """SemanticCacheIndexSchema is built from vectorizer.dims/dtype (1024/float32)."""
        vectorizer = _make_vectorizer()
        assert vectorizer.dims == BGE_DENSE_DIMS
        assert vectorizer.dtype == "float32"

    def test_construction_makes_no_bge_calls(self) -> None:
        """Vectorizers are built on every cache initialize(); none may call BGE."""
        instance = MagicMock()
        instance.encode_dense = AsyncMock()
        class_mock = MagicMock(return_value=instance)
        with patch("src.services.bge_m3_client.BGEM3Client", class_mock):
            _make_vectorizer()
        class_mock.assert_not_called()
        instance.encode_dense.assert_not_called()

    async def test_aembed_single_calls_encode_dense_once(self) -> None:
        vector = [0.1] * BGE_DENSE_DIMS
        _class_mock, instance, patcher = _patched_bge([vector])
        with patcher:
            vectorizer = _make_vectorizer()
            result = await vectorizer.aembed("как оформить внж")
        assert result == vector
        instance.encode_dense.assert_awaited_once_with(["как оформить внж"])

    async def test_aembed_many_calls_encode_dense_once_with_full_batch(self) -> None:
        """Batch parity: one encode_dense call with the whole list (no chunking)."""
        texts = ["вопрос один", "вопрос два", "вопрос три"]
        vectors = [[0.1] * BGE_DENSE_DIMS for _ in texts]
        _class_mock, instance, patcher = _patched_bge(vectors)
        with patcher:
            vectorizer = _make_vectorizer()
            result = await vectorizer.aembed_many(texts)
        assert result == vectors
        instance.encode_dense.assert_awaited_once_with(texts)

    async def test_bge_client_created_lazily_once_and_reused(self) -> None:
        """Two embed operations share one lazily-created BGEM3Client."""
        vectors = [[0.2] * BGE_DENSE_DIMS]
        class_mock, instance, patcher = _patched_bge(vectors)
        with patcher:
            vectorizer = _make_vectorizer()
            await vectorizer.aembed("первый")
            await vectorizer.aembed_many(["второй"])
        assert class_mock.call_count == 1
        assert instance.encode_dense.await_count == 2


class TestSyncEmbedSurfaceDelta:
    """Documents the sync surface per implementation.

    #3389 accepted delta: the sync surface changed from
    ``NotImplementedError`` (archived ``BgeM3CacheVectorizer`` subclass) to
    the local zero-vector dims probe — the official ``CustomVectorizer``
    validates dims through the sync callable at construction. Production
    never calls the sync surface: ``check_semantic`` / ``store_semantic``
    always pass ``vector=`` explicitly. Updated together with the refactor.
    """

    def test_sync_embed_is_local_probe_without_bge(self) -> None:
        instance = MagicMock()
        instance.encode_dense = AsyncMock()
        class_mock = MagicMock(return_value=instance)
        with patch("src.services.bge_m3_client.BGEM3Client", class_mock):
            vectorizer = _make_vectorizer()
            single = vectorizer.embed("текст")
            batch = vectorizer.embed_many(["вопрос один", "вопрос два"])
        class_mock.assert_not_called()
        instance.encode_dense.assert_not_called()
        assert single == [0.0] * BGE_DENSE_DIMS
        assert batch == [[0.0] * BGE_DENSE_DIMS, [0.0] * BGE_DENSE_DIMS]
