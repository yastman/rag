"""Generation setup resolution — query, style, coverage, sources (#3015)."""

from __future__ import annotations

from typing import Any

from src.runtime.grounding.policy import is_strict_grounding_safe
from src.runtime.services.coverage_mode import detect_coverage_mode
from src.runtime.services.metrics import PipelineMetrics
from src.runtime.services.response_style_detector import ResponseStyleDetector

from .contracts import GenerationRequest
from .messages import _select_recent_history
from .policy import _MAX_HISTORY_MESSAGES


class _GenerationSetup:
    """Resolved common setup values shared between generate_answer and generate_answer_stream."""

    __slots__ = (
        "coverage_reason",
        "effective_query",
        "legal_answer_safe",
        "needs_coverage",
        "sources_enabled",
        "style_info",
    )

    def __init__(
        self,
        *,
        effective_query: str,
        style_info: Any,
        needs_coverage: bool,
        coverage_reason: str | None,
        sources_enabled: bool,
        legal_answer_safe: bool,
    ) -> None:
        self.effective_query = effective_query
        self.style_info = style_info
        self.needs_coverage = needs_coverage
        self.coverage_reason = coverage_reason
        self.sources_enabled = sources_enabled
        self.legal_answer_safe = legal_answer_safe


def _resolve_generation_setup(
    request: GenerationRequest,
    dyn: dict[str, Any],
) -> _GenerationSetup:
    """Resolve query, style, coverage, sources, and legal-answer-safe for a generation request."""
    extra = request.extra_kwargs or {}
    docs = request.documents or []
    raw_history = request.raw_messages or []
    messages = _select_recent_history(raw_history, _MAX_HISTORY_MESSAGES)

    effective_query = request.query
    if not effective_query and messages:
        last_msg = messages[-1]
        effective_query = (
            last_msg.get("content", "")
            if isinstance(last_msg, dict)
            else getattr(last_msg, "content", "")
        )

    detector = extra.get("style_detector") or dyn["ResponseStyleDetector"]()
    style_info = detector.detect(effective_query)

    coverage_decision = dyn["detect_coverage_mode"](effective_query)
    needs_coverage = bool(extra.get("needs_coverage", False)) or coverage_decision.needs_coverage
    coverage_reason = coverage_decision.reason or (
        "state:needs_coverage" if needs_coverage else None
    )

    sources_enabled = bool(
        getattr(request.config, "show_sources", False) or request.grounding_mode == "strict"
    )
    legal_answer_safe = request.grounding_mode != "strict" or is_strict_grounding_safe(
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
    )

    return _GenerationSetup(
        effective_query=effective_query,
        style_info=style_info,
        needs_coverage=needs_coverage,
        coverage_reason=coverage_reason,
        sources_enabled=sources_enabled,
        legal_answer_safe=legal_answer_safe,
    )


def _get_dynamic_modules(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retrieve overridable runtime dependencies for generation tests."""
    from src.runtime.integrations.prompt_manager import (
        get_prompt,
        get_prompt_with_config,
        get_prompt_with_object,
    )
    from src.runtime.integrations.prompt_templates import (
        build_system_prompt_with_manager,
        get_token_limit,
    )

    modules = {
        "get_prompt": get_prompt,
        "get_prompt_with_config": get_prompt_with_config,
        "get_prompt_with_object": get_prompt_with_object,
        "build_system_prompt_with_manager": build_system_prompt_with_manager,
        "get_token_limit": get_token_limit,
        "ResponseStyleDetector": ResponseStyleDetector,
        "detect_coverage_mode": detect_coverage_mode,
        "PipelineMetrics": PipelineMetrics,
    }
    if extra:
        for k in list(modules.keys()):
            if k in extra:
                modules[k] = extra[k]
    return modules
