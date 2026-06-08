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
