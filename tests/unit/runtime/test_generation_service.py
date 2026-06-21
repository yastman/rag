"""Tests for the runtime generation seam."""

from __future__ import annotations


async def test_generate_answer_uses_transport_free_request_contract() -> None:
    from src.runtime.generation import GenerationRequest, generate_answer

    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return {"response": "hello", "llm_provider_model": "fake"}

    result = await generate_answer(
        GenerationRequest(
            query="q",
            documents=[{"text": "fact"}],
            grounding_mode="strict",
            grade_confidence=0.7,
            config=object(),
        ),
        generate=fake_generate,
    )

    assert result.response_text == "hello"
    assert captured["query"] == "q"
    assert captured["documents"] == [{"text": "fact"}]
    assert captured["grounding_mode"] == "strict"
    assert captured["grade_confidence"] == 0.7
    assert "message" not in captured


import pytest


@pytest.mark.asyncio
async def test_generate_answer_raises_value_error_when_config_is_none() -> None:
    """config=None must raise ValueError (not AssertionError) — survives python -O."""
    from src.runtime.generation import GenerationRequest, generate_answer

    with pytest.raises(ValueError, match=r"GenerationRequest\.config must be set"):
        await generate_answer(
            GenerationRequest(
                query="q",
                documents=[],
                grounding_mode="strict",
                grade_confidence=0.7,
                config=None,
            )
        )


@pytest.mark.asyncio
async def test_generate_answer_stream_raises_value_error_when_config_is_none() -> None:
    """config=None must raise ValueError (not AssertionError) — survives python -O."""
    from src.runtime.generation import GenerationRequest
    from src.runtime.generation.service import generate_answer_stream

    with pytest.raises(ValueError, match=r"GenerationRequest\.config must be set"):
        async for _ in generate_answer_stream(
            GenerationRequest(
                query="q",
                documents=[],
                grounding_mode="strict",
                grade_confidence=0.7,
                config=None,
            ),
            metadata_out={},
        ):
            pass
