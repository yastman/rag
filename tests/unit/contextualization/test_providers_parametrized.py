"""Parametrized contextualization-provider scenarios (#2068).

Consolidates the truly identical Claude/OpenAI/Groq tests that used to be
copy-pasted across ``test_claude.py``, ``test_openai.py`` and
``test_groq.py``. Each scenario runs once per provider via the shared
:class:`ProviderSpec` kit.

Provider-specific behaviour stays in the per-provider files. See:

* ``test_claude.py`` — prompt caching, cost rounding, partial-failure pattern
* ``test_openai.py`` — Langfuse drop-in import, SDK retry contract
* ``test_groq.py`` — free-tier stats, settings-temperature handling, batch
  warning logging
"""

from __future__ import annotations

import pytest

from src.contextualization.base import ContextualizedChunk

from ._provider_kit import (
    ALL_PROVIDERS,
    ProviderSpec,
    make_contextualizer,
    patch_create,
)


@pytest.fixture(params=ALL_PROVIDERS, ids=lambda spec: spec.name)
def provider(request) -> ProviderSpec:
    return request.param


@pytest.fixture
def contextualizer(provider: ProviderSpec):
    return make_contextualizer(provider)


# ---------------------------------------------------------------------------
# contextualize() — happy paths
# ---------------------------------------------------------------------------


async def test_contextualize_single_chunk(contextualizer, provider: ProviderSpec):
    """Single chunk → single ContextualizedChunk with provider label."""
    response = provider.response_factory("Contextual summary")
    patch_create(contextualizer, provider, return_value=response)

    chunks = ["This is the legal text to contextualize."]
    results = await contextualizer.contextualize(chunks)

    assert len(results) == 1
    assert isinstance(results[0], ContextualizedChunk)
    assert results[0].original_text == chunks[0]
    assert results[0].contextual_summary == "Contextual summary"
    assert results[0].article_number == "chunk_0"
    assert results[0].context_method == provider.name


async def test_contextualize_multiple_chunks(contextualizer, provider: ProviderSpec):
    """Multiple chunks → indices and per-chunk summaries preserved."""
    responses = [provider.response_factory(f"Summary {i}") for i in range(3)]
    create_mock = patch_create(contextualizer, provider, side_effect=responses)

    chunks = ["Chunk 1 text", "Chunk 2 text", "Chunk 3 text"]
    results = await contextualizer.contextualize(chunks)

    assert len(results) == 3
    for i, result in enumerate(results):
        assert result.original_text == chunks[i]
        assert result.contextual_summary == f"Summary {i}"
        assert result.article_number == f"chunk_{i}"
    assert create_mock.call_count == 3


async def test_contextualize_with_query(contextualizer, provider: ProviderSpec):
    """Optional query parameter is forwarded into contextualize_single()."""
    response = provider.response_factory("Query-aware summary")
    create_mock = patch_create(contextualizer, provider, return_value=response)

    chunks = ["Legal text"]
    results = await contextualizer.contextualize(chunks, query="What are the penalties?")

    assert len(results) == 1
    assert results[0].contextual_summary == "Query-aware summary"
    create_mock.assert_called_once()


# ---------------------------------------------------------------------------
# contextualize() — empty input + error paths
# ---------------------------------------------------------------------------


async def test_contextualize_empty_chunks(contextualizer, provider: ProviderSpec):
    """Empty list short-circuits without calling the vendor SDK."""
    create_mock = patch_create(contextualizer, provider)

    results = await contextualizer.contextualize([])

    assert results == []
    create_mock.assert_not_called()


async def test_contextualize_handles_api_error_gracefully(contextualizer, provider: ProviderSpec):
    """API errors result in fallback chunks (context_method='none')."""
    patch_create(
        contextualizer,
        provider,
        side_effect=Exception("API error"),
    )

    chunks = ["Text that will fail"]
    results = await contextualizer.contextualize(chunks)

    assert len(results) == 1
    assert results[0].original_text == chunks[0]
    assert results[0].contextual_summary == ""  # Fallback marker
    assert results[0].context_method == "none"
