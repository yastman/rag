"""Regression tests for generate_answer / generate_answer_stream shared helper logic.

These characterization tests pin the behavior of the shared blocks:
- _resolve_generation_setup: query/style/coverage/sources/legal-answer-safe resolution
- _select_prompt_config: coverage/style/default prompt selection
- _build_llm_messages: history + user content assembly
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.runtime.generation.contracts import GenerationRequest
from src.runtime.generation.service import (
    _build_llm_messages,
    _resolve_generation_setup,
    _select_prompt_config,
)
from src.runtime.services.coverage_mode import CoverageDecision
from src.runtime.services.response_style_detector import StyleInfo


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeStyleDetector:
    def __init__(self, style: str = "balanced", difficulty: str = "medium") -> None:
        self._style = style
        self._difficulty = difficulty

    def detect(self, query: str) -> StyleInfo:
        return StyleInfo(
            style=self._style,
            difficulty=self._difficulty,
            reasoning="test",
            word_count=len(query.split()),
        )


def _config(
    *,
    show_sources: bool = False,
    style_enabled: bool = False,
    shadow_mode: bool = False,
    max_tokens: int = 512,
    domain: str = "test_domain",
    temperature: float = 0.2,
) -> MagicMock:
    cfg = MagicMock()
    cfg.show_sources = show_sources
    cfg.response_style_enabled = style_enabled
    cfg.response_style_shadow_mode = shadow_mode
    cfg.generate_max_tokens = max_tokens
    cfg.domain = domain
    cfg.llm_temperature = temperature
    return cfg


def _dyn(
    *, coverage: bool = False, style_prompt: str = "style_sys", style_budget: int = 400
) -> dict:
    return {
        "ResponseStyleDetector": _FakeStyleDetector,
        "detect_coverage_mode": lambda _: CoverageDecision(
            coverage, "test_reason" if coverage else None
        ),
        "get_prompt_with_config": lambda name, **_kw: (f"sys:{name}", {"max_tokens": 200}),
        "get_prompt_with_object": lambda _n, **_kw: (None, None),
        "build_system_prompt_with_manager": lambda **_kw: style_prompt,
        "get_token_limit": lambda _s, _d: style_budget,
    }


# ---------------------------------------------------------------------------
# _resolve_generation_setup
# ---------------------------------------------------------------------------


def test_resolve_setup_derives_query_from_last_message() -> None:
    request = GenerationRequest(
        query="",
        documents=[],
        raw_messages=[{"role": "user", "content": "what is the price?"}],
        grounding_mode="default",
        config=_config(),
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.effective_query == "what is the price?"


def test_resolve_setup_prefers_explicit_query_over_message() -> None:
    request = GenerationRequest(
        query="explicit query",
        documents=[],
        raw_messages=[{"role": "user", "content": "message content"}],
        grounding_mode="default",
        config=_config(),
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.effective_query == "explicit query"


def test_resolve_setup_sources_enabled_when_strict_grounding() -> None:
    request = GenerationRequest(
        query="q",
        documents=[{"content": "doc"}],
        grounding_mode="strict",
        grade_confidence=0.9,
        config=_config(show_sources=False),
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.sources_enabled is True


def test_resolve_setup_sources_enabled_when_show_sources_config() -> None:
    request = GenerationRequest(
        query="q",
        documents=[],
        grounding_mode="default",
        config=_config(show_sources=True),
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.sources_enabled is True


def test_resolve_setup_needs_coverage_from_detector() -> None:
    request = GenerationRequest(
        query="перечислите все",
        documents=[],
        grounding_mode="default",
        config=_config(),
    )
    result = _resolve_generation_setup(request, _dyn(coverage=True))
    assert result.needs_coverage is True
    assert result.coverage_reason is not None


def test_resolve_setup_needs_coverage_from_extra_flag() -> None:
    request = GenerationRequest(
        query="q",
        documents=[],
        grounding_mode="default",
        config=_config(),
        extra_kwargs={"needs_coverage": True},
    )
    result = _resolve_generation_setup(request, _dyn(coverage=False))
    assert result.needs_coverage is True


def test_resolve_setup_legal_answer_safe_strict_no_docs() -> None:
    request = GenerationRequest(
        query="q",
        documents=[],
        grounding_mode="strict",
        grade_confidence=0.1,
        config=_config(show_sources=True),
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.legal_answer_safe is False


def test_resolve_setup_legal_answer_safe_non_strict() -> None:
    request = GenerationRequest(
        query="q",
        documents=[],
        grounding_mode="default",
        config=_config(),
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.legal_answer_safe is True


def test_resolve_setup_style_info_populated() -> None:
    request = GenerationRequest(
        query="hello world",
        documents=[],
        grounding_mode="default",
        config=_config(),
        extra_kwargs={"style_detector": _FakeStyleDetector("concise", "easy")},
    )
    result = _resolve_generation_setup(request, _dyn())
    assert result.style_info.style == "concise"
    assert result.style_info.difficulty == "easy"


# ---------------------------------------------------------------------------
# _select_prompt_config
# ---------------------------------------------------------------------------


def test_select_prompt_coverage_path() -> None:
    cfg = _config(max_tokens=512)
    dyn = _dyn(coverage=True)
    result = _select_prompt_config(
        config=cfg,
        needs_coverage=True,
        use_style=False,
        style_info=_FakeStyleDetector().detect("q"),
        dyn=dyn,
        extra={},
    )
    assert result.response_policy_mode == "coverage"
    assert result.prompt_name == "generate_exhaustive_list"
    assert result.system_prompt.startswith("sys:generate_exhaustive_list")
    assert result.max_tokens <= 512


def test_select_prompt_style_path() -> None:
    cfg = _config(style_enabled=True, max_tokens=512)
    dyn = _dyn(style_prompt="style_sys_prompt", style_budget=300)
    extra = {
        "style_prompt_builder": lambda **_kw: "custom_style_sys",
        "style_token_limit": lambda _s, _d: 250,
    }
    result = _select_prompt_config(
        config=cfg,
        needs_coverage=False,
        use_style=True,
        style_info=_FakeStyleDetector().detect("q"),
        dyn=dyn,
        extra=extra,
    )
    assert result.response_policy_mode == "enforced"
    assert result.prompt_name == "generate"
    assert result.system_prompt == "custom_style_sys"
    assert result.max_tokens == min(250, 512)


def test_select_prompt_default_path() -> None:
    cfg = _config(max_tokens=512)
    dyn = _dyn()
    result = _select_prompt_config(
        config=cfg,
        needs_coverage=False,
        use_style=False,
        style_info=_FakeStyleDetector().detect("q"),
        dyn=dyn,
        extra={},
    )
    assert result.response_policy_mode == "disabled"
    assert result.prompt_name == "generate"
    assert result.system_prompt.startswith("sys:generate")


def test_select_prompt_shadow_mode_policy() -> None:
    cfg = _config(style_enabled=True, shadow_mode=True, max_tokens=512)
    dyn = _dyn()
    result = _select_prompt_config(
        config=cfg,
        needs_coverage=False,
        use_style=False,  # shadow disables use_style
        style_info=_FakeStyleDetector().detect("q"),
        dyn=dyn,
        extra={},
    )
    assert result.response_policy_mode == "shadow"


# ---------------------------------------------------------------------------
# _build_llm_messages
# ---------------------------------------------------------------------------


def test_build_llm_messages_basic_structure() -> None:
    docs_text = "some context"
    msgs = _build_llm_messages(
        system_prompt="You are helpful.",
        raw_history=[{"role": "user", "content": "previous question"}],
        effective_query="new question",
        context=docs_text,
        extra={},
    )
    assert msgs[0] == {"role": "system", "content": "You are helpful."}
    assert msgs[-1]["role"] == "user"
    assert "new question" in msgs[-1]["content"]
    assert docs_text in msgs[-1]["content"]


def test_build_llm_messages_includes_history_except_last() -> None:
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]
    msgs = _build_llm_messages(
        system_prompt="sys",
        raw_history=history,
        effective_query="q2",
        context="ctx",
        extra={},
    )
    # system + q1 + a1 + final user content (q2 in context)
    roles = [m["role"] for m in msgs]
    assert roles[0] == "system"
    assert "user" in roles
    assert "assistant" in roles
    # Last message is the formatted user content
    assert msgs[-1]["role"] == "user"
    assert "q2" in msgs[-1]["content"]


def test_build_llm_messages_maps_human_role() -> None:
    # 3-item history so both human+ai appear in messages[:-1]
    history = [
        {"role": "human", "content": "hi"},
        {"role": "ai", "content": "hello"},
        {"role": "human", "content": "followup"},
    ]
    msgs = _build_llm_messages(
        system_prompt="sys",
        raw_history=history,
        effective_query="followup",
        context="ctx",
        extra={},
    )
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assert "assistant" in roles
    assert "human" not in roles
    assert "ai" not in roles


def test_build_llm_messages_empty_history() -> None:
    msgs = _build_llm_messages(
        system_prompt="sys",
        raw_history=[],
        effective_query="only question",
        context="ctx",
        extra={},
    )
    assert len(msgs) == 2  # system + user
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
