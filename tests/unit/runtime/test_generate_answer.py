"""Focused unit tests for generate_answer (src/runtime/generation/service.py).

Three scenarios, no live LLM key:
1. Happy path — LLM responds; result carries answer + grounded=True
2. LLM failure fallback — exception during LLM call → reasonable response, no raise
3. Low-grounding / safe-fallback — strict grounding mode with low-confidence docs →
   returns safe_fallback_used=True, no LLM call
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.runtime.generation.contracts import GenerationRequest
from src.runtime.generation.service import generate_answer
from src.runtime.services.coverage_mode import CoverageDecision
from src.runtime.services.response_style_detector import StyleInfo


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


def _fake_style_detector():
    detector = MagicMock()
    detector.detect.return_value = StyleInfo(
        style="balanced", difficulty="medium", reasoning="test", word_count=3
    )
    return detector


def _base_dyn(detector=None):
    """Minimal dynamic-module overrides so no real services are loaded."""
    return {
        "ResponseStyleDetector": lambda: detector or _fake_style_detector(),
        "detect_coverage_mode": lambda _q: CoverageDecision(False, None),
        "get_prompt_with_config": lambda name, **_kw: (f"sys:{name}", {"max_tokens": 200}),
        "get_prompt_with_object": lambda _n, **_kw: (None, None),
        "build_system_prompt_with_manager": lambda **_kw: "style_sys",
        "get_token_limit": lambda _s, _d: 400,
        "PipelineMetrics": MagicMock(get=MagicMock(return_value=MagicMock(record=MagicMock()))),
    }


def _fake_response(text: str, model: str = "gpt-test") -> MagicMock:
    """Build a minimal OpenAI-style response object."""
    choice = SimpleNamespace(message=SimpleNamespace(content=text))
    usage = SimpleNamespace(completion_tokens=10)
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = model
    return resp


def _config(*, show_sources: bool = False) -> MagicMock:
    cfg = MagicMock()
    cfg.show_sources = show_sources
    cfg.response_style_enabled = False
    cfg.response_style_shadow_mode = False
    cfg.generate_max_tokens = 512
    cfg.domain = "real-estate"
    cfg.llm_temperature = 0.2
    cfg.llm_model = "gpt-test"
    cfg.get_reasoning_kwargs.return_value = {}
    return cfg


# ---------------------------------------------------------------------------
# Test 1: Happy path — LLM responds, citations/grounding in result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_happy_path() -> None:
    """LLM call succeeds → answer is returned, grounded=True, llm_call_count incremented."""
    llm_mock = MagicMock()
    llm_mock.chat.completions.create = AsyncMock(
        return_value=_fake_response("Квартира стоит 80 000€")
    )

    cfg = _config(show_sources=False)
    cfg.create_llm.return_value = llm_mock

    dyn = _base_dyn()
    request = GenerationRequest(
        query="Сколько стоит квартира?",
        documents=[{"metadata": {"title": "Апартамент A1"}, "content": "Цена 80 000€"}],
        grounding_mode="normal",
        llm_call_count=0,
        config=cfg,
        extra_kwargs=dyn,
    )

    result = await generate_answer(request)

    assert result.response_text  # non-empty answer
    assert result.payload["grounded"] is True
    assert result.payload["safe_fallback_used"] is False
    assert result.payload["llm_call_count"] == 1
    assert result.payload["llm_provider_model"] == "gpt-test"


# ---------------------------------------------------------------------------
# Test 2: LLM failure fallback — exception → reasonable answer, no raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_llm_failure_returns_fallback() -> None:
    """When the LLM raises, generate_answer returns a fallback response instead of propagating."""
    llm_mock = MagicMock()
    llm_mock.chat.completions.create = AsyncMock(side_effect=RuntimeError("connection refused"))

    cfg = _config()
    cfg.create_llm.return_value = llm_mock

    dyn = _base_dyn()
    request = GenerationRequest(
        query="Что такое рассрочка?",
        documents=[
            {
                "metadata": {"title": "Объект B2", "price": 95000, "city": "Варна"},
                "content": "Рассрочка доступна",
            }
        ],
        grounding_mode="normal",
        llm_call_count=1,
        config=cfg,
        extra_kwargs=dyn,
    )

    # Must not raise
    result = await generate_answer(request)

    assert result.response_text  # non-empty fallback
    assert result.payload["llm_provider_model"] == "fallback"
    assert result.payload["grounded"] is False
    assert result.payload["llm_timeout"] is True


# ---------------------------------------------------------------------------
# Test 3: Low-grounding / safe-fallback path (strict mode, low confidence)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_answer_safe_fallback_on_low_grounding() -> None:
    """strict grounding mode + low confidence → safe_fallback_used=True, LLM is never called."""
    llm_mock = MagicMock()
    llm_mock.chat.completions.create = AsyncMock()  # should NOT be called

    cfg = _config(show_sources=True)  # show_sources=True enables sources (required for strict)
    cfg.create_llm.return_value = llm_mock

    dyn = _base_dyn()
    request = GenerationRequest(
        query="Каков правовой статус объекта?",
        documents=[],  # empty docs → not strict-grounding-safe
        grounding_mode="strict",
        grade_confidence=0.1,  # below threshold
        llm_call_count=0,
        config=cfg,
        extra_kwargs=dyn,
    )

    result = await generate_answer(request)

    assert result.payload["safe_fallback_used"] is True
    assert result.payload["grounded"] is False
    assert result.payload["llm_provider_model"] == "safe_fallback"
    # LLM was never invoked
    llm_mock.chat.completions.create.assert_not_called()
