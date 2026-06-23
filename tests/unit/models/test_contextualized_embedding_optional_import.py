"""Regression tests for optional voyageai imports."""

from __future__ import annotations

import importlib
import importlib.abc
import sys

import pytest


class _BlockVoyageAI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname == "voyageai" or fullname.startswith("voyageai."):
            raise ModuleNotFoundError("blocked voyageai for optional import test")
        return


@pytest.fixture
def voyageai_unavailable(monkeypatch: pytest.MonkeyPatch):
    for name in list(sys.modules):
        if name == "voyageai" or name.startswith("voyageai."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delitem(sys.modules, "src.models.contextualized_embedding", raising=False)
    finder = _BlockVoyageAI()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


def test_contextualized_embedding_module_import_does_not_require_voyageai(
    voyageai_unavailable: None,
) -> None:
    module = importlib.import_module("src.models.contextualized_embedding")

    assert module.ContextualizedEmbeddingResult(
        embeddings=[], total_tokens=0, chunks_per_document=[]
    )


def test_contextualized_embedding_service_reports_missing_voyage_extra(
    voyageai_unavailable: None,
) -> None:
    module = importlib.import_module("src.models.contextualized_embedding")

    with pytest.raises(RuntimeError, match="uv sync --extra voyage"):
        module.ContextualizedEmbeddingService(api_key="test-key")
