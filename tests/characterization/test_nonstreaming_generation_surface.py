"""Characterization: the non-streaming generation contract (#3481).

Pins the surviving non-streaming ``generate_answer`` behavior across the
removal of the test-only streaming runtime surface (#3481):

- the live path drives the one-shot ``completion`` verb and never the
  router-boundary ``stream`` verb;
- the strict-grounding safe fallback skips the LLM entirely and stays
  cache-unsafe;
- provider usage/token metrics survive on the non-streaming payload.

The Telegram one-send boundary is pinned separately by
``tests/unit/test_bot_query_supervisor.py::test_single_core_call_no_telegram_classify_embed_cache``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.runtime.generation.contracts import GenerationRequest
from src.runtime.generation.service import generate_answer
from src.runtime.services.coverage_mode import CoverageDecision
from src.runtime.services.response_style_detector import StyleInfo


class _RecordingLLM:
    """One-shot LLM double that records both completion and stream verb usage."""

    def __init__(self, answer: str, model: str = "characterization-model") -> None:
        self._answer = answer
        self._model = model
        self.completion_calls = 0
        self.stream_calls = 0

    async def completion(self, **_kwargs: Any) -> Any:
        self.completion_calls += 1
        return SimpleNamespace(
            model=self._model,
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=48, total_tokens=168),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._answer))],
        )

    def stream(self, **_kwargs: Any) -> Any:
        self.stream_calls += 1
        raise AssertionError("generate_answer must not use the streaming verb")

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        return {}


class _Config:
    """GraphConfig-compatible config serving the recording LLM."""

    domain = "недвижимость в Болгарии"
    llm_model = "characterization-model"
    llm_temperature = 0.0
    generate_max_tokens = 512
    show_sources = False
    response_style_enabled = False
    response_style_shadow_mode = False

    def __init__(self, llm: _RecordingLLM) -> None:
        self._llm = llm

    def create_llm(self, *, auto_trace: bool = False) -> Any:
        return self._llm

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        return {}


def _base_dyn() -> dict[str, Any]:
    """Hermetic dynamic-module overrides so no real services load."""
    detector = SimpleNamespace(
        detect=lambda query: StyleInfo(
            style="balanced",
            difficulty="medium",
            reasoning="characterization",
            word_count=len(query.split()),
        )
    )
    return {
        "ResponseStyleDetector": lambda: detector,
        "detect_coverage_mode": lambda _query: CoverageDecision(False, None),
        "get_prompt_with_config": lambda name, **_kw: (f"sys:{name}", {"max_tokens": 200}),
        "get_prompt_with_object": lambda _n, **_kw: (None, None),
        "build_system_prompt_with_manager": lambda **_kw: "style_sys",
        "get_token_limit": lambda _s, _d: 400,
        "PipelineMetrics": SimpleNamespace(
            get=lambda: SimpleNamespace(record=lambda *_a, **_kw: None)
        ),
    }


def _request(llm: _RecordingLLM, **overrides: Any) -> GenerationRequest:
    defaults: dict[str, Any] = {
        "query": "Сколько стоит квартира в Sunny Beach?",
        "documents": [
            {
                "content": "Цена 115 000 EUR, акт 16 выдан.",
                "metadata": {"title": "Sunny Beach", "score": 0.9},
            }
        ],
        "grounding_mode": "normal",
        "llm_call_count": 0,
        "config": _Config(llm),
        "extra_kwargs": _base_dyn(),
    }
    defaults.update(overrides)
    return GenerationRequest(**defaults)


@pytest.mark.asyncio
async def test_generate_answer_drives_completion_never_stream() -> None:
    """Happy path: one-shot completion only, with surviving usage/token metrics."""
    llm = _RecordingLLM("Стоимость 115 000 EUR, акт 16 выдан.")

    result = await generate_answer(_request(llm))

    assert result.response_text == "Стоимость 115 000 EUR, акт 16 выдан."
    assert llm.completion_calls == 1
    assert llm.stream_calls == 0
    assert result.payload["grounded"] is True
    assert result.payload["safe_fallback_used"] is False
    assert result.payload["llm_timeout"] is False
    assert result.payload["llm_call_count"] == 1
    assert result.payload["llm_provider_model"] == "characterization-model"
    assert result.payload["usage_details"] == {"input": 120, "output": 48, "total": 168}
    assert result.payload["llm_ttft_ms"] > 0
    assert result.payload["llm_tps"] > 0


@pytest.mark.asyncio
async def test_strict_fallback_skips_llm_and_stays_cache_unsafe() -> None:
    """Strict grounding + no safe docs: fallback answer without touching the LLM at all."""
    llm = _RecordingLLM("не должен вызываться")

    result = await generate_answer(
        _request(
            llm,
            documents=[],
            grounding_mode="strict",
            grade_confidence=0.05,
        )
    )

    assert result.response_text.strip()
    assert llm.completion_calls == 0
    assert llm.stream_calls == 0
    assert result.payload["safe_fallback_used"] is True
    assert result.payload["grounded"] is False
    assert result.payload["llm_provider_model"] == "safe_fallback"
    assert result.payload["semantic_cache_safe_reuse"] is False
    assert result.payload["llm_call_count"] == 0
