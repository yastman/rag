"""Focused tests for runtime generation streaming helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.runtime.generation.contracts import GenerationRequest
from src.runtime.generation.service import generate_answer_stream
from src.runtime.services.coverage_mode import CoverageDecision
from src.runtime.services.response_style_detector import StyleInfo


class _StyleDetector:
    def detect(self, query: str) -> StyleInfo:
        return StyleInfo(
            style="balanced",
            difficulty="medium",
            reasoning="test_style",
            word_count=len(query.split()),
        )


class _Metrics:
    def __init__(self) -> None:
        self.record = MagicMock()


class _PipelineMetrics:
    metric = _Metrics()

    @classmethod
    def get(cls) -> _Metrics:
        return cls.metric


@pytest.mark.asyncio
async def test_generate_answer_stream_safe_fallback_preserves_metadata_and_skips_llm() -> None:
    config = MagicMock()
    config.show_sources = True
    config.response_style_enabled = False
    config.response_style_shadow_mode = False
    config.generate_max_tokens = 128
    config.domain = "недвижимость"
    config.create_llm = MagicMock()

    lf_client = MagicMock()
    metadata_out: dict[str, object] = {}
    fallback_answer = "Не могу дать надежный ответ по найденному контексту."
    _PipelineMetrics.metric = _Metrics()

    request = GenerationRequest(
        query="Можно ли получить ВНЖ?",
        documents=[],
        raw_messages=[{"role": "user", "content": "Можно ли получить ВНЖ?"}],
        latency_stages={"retrieve": 0.25},
        llm_call_count=2,
        grounding_mode="strict",
        grade_confidence=0.1,
        config=config,
        extra_kwargs={
            "lf_client": lf_client,
            "style_detector": _StyleDetector(),
            "detect_coverage_mode": lambda _query: CoverageDecision(False, None),
            "PipelineMetrics": _PipelineMetrics,
            "build_fallback_response": lambda _docs: fallback_answer,
        },
    )

    chunks = [chunk async for chunk in generate_answer_stream(request, metadata_out)]

    assert chunks == [fallback_answer]
    assert metadata_out["response"] == fallback_answer
    assert metadata_out["safe_fallback_used"] is True
    assert metadata_out["grounded"] is False
    assert metadata_out["legal_answer_safe"] is False
    assert metadata_out["semantic_cache_safe_reuse"] is False
    assert metadata_out["streaming_enabled"] is True
    assert metadata_out["llm_call_count"] == 2
    assert metadata_out["latency_stages"]["retrieve"] == 0.25  # type: ignore[index]
    assert "generate" in metadata_out["latency_stages"]  # type: ignore[operator]
    assert metadata_out["needs_coverage"] is False
    assert metadata_out["response_style"] == "balanced"
    assert metadata_out["response_difficulty"] == "medium"
    assert metadata_out["response_style_reasoning"] == "test_style"
    assert metadata_out["response_policy_mode"] == "safe_fallback"
    assert metadata_out["llm_provider_model"] == "safe_fallback"

    span_outputs = [
        call.kwargs["output"]
        for call in lf_client.update_current_span.call_args_list
        if "output" in call.kwargs
    ]
    assert span_outputs[-1]["safe_fallback_used"] is True
    assert span_outputs[-1]["grounded"] is False
    assert span_outputs[-1]["llm_provider_model"] == "safe_fallback"
    assert span_outputs[-1]["needs_coverage"] is False
    _PipelineMetrics.metric.record.assert_called_once()
    config.create_llm.assert_not_called()
