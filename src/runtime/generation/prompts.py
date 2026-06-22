"""Prompt selection, message assembly, and context formatting (#3015)."""

from __future__ import annotations

import inspect
from typing import Any

from .context import _MAX_CONTEXT_DOCS, _format_context
from .messages import _build_llm_messages, _ensure_history_instruction
from .policy import (
    _CITATION_INSTRUCTION,
    _EXHAUSTIVE_GENERATE_FALLBACK,
    _GENERATE_FALLBACK,
)


class _PromptConfig:
    """Resolved prompt/token config shared between generate_answer and generate_answer_stream."""

    __slots__ = (
        "max_tokens",
        "prompt_config",
        "prompt_name",
        "response_policy_mode",
        "system_prompt",
    )

    def __init__(
        self,
        *,
        system_prompt: str,
        max_tokens: int,
        prompt_name: str,
        prompt_config: dict[str, Any],
        response_policy_mode: str,
    ) -> None:
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.prompt_name = prompt_name
        self.prompt_config = prompt_config
        self.response_policy_mode = response_policy_mode


class _PromptAndMessages:
    """Resolved prompt, temperature, and LLM messages for a generation call."""

    __slots__ = (
        "effective_temperature",
        "llm_messages",
        "max_tokens",
        "prompt_name",
        "response_policy_mode",
    )

    def __init__(
        self,
        *,
        effective_temperature: float,
        llm_messages: list[dict[str, str]],
        max_tokens: int,
        prompt_name: str,
        response_policy_mode: str,
    ) -> None:
        self.effective_temperature = effective_temperature
        self.llm_messages = llm_messages
        self.max_tokens = max_tokens
        self.prompt_name = prompt_name
        self.response_policy_mode = response_policy_mode


def _select_prompt_config(
    *,
    config: Any,
    needs_coverage: bool,
    use_style: bool,
    style_info: Any,
    dyn: dict[str, Any],
    extra: dict[str, Any],
) -> _PromptConfig:
    """Select system prompt, token budget, and policy mode for a generation call."""
    legacy_max_tokens = int(config.generate_max_tokens)
    prompt_config: dict[str, Any] = {}
    prompt_name = "generate"

    if needs_coverage:
        system_prompt, prompt_config = dyn["get_prompt_with_config"](
            "generate_exhaustive_list",
            fallback=_EXHAUSTIVE_GENERATE_FALLBACK,
            variables={"domain": config.domain},
        )
        max_tokens = (
            min(int(prompt_config["max_tokens"]), legacy_max_tokens)
            if "max_tokens" in prompt_config
            else legacy_max_tokens
        )
        response_policy_mode = "coverage"
        prompt_name = "generate_exhaustive_list"
    elif use_style:
        style_prompt_builder = (
            extra.get("style_prompt_builder") or dyn["build_system_prompt_with_manager"]
        )
        system_prompt = style_prompt_builder(
            style=style_info.style,
            difficulty=style_info.difficulty,
            domain=config.domain,
        )
        style_token_limit = extra.get("style_token_limit") or dyn["get_token_limit"]
        style_budget = style_token_limit(style_info.style, style_info.difficulty)
        max_tokens = min(style_budget, legacy_max_tokens)
        response_policy_mode = "enforced"
    else:
        build_sys_prompt_config_fn = extra.get("build_system_prompt_with_config")
        build_sys_prompt_fn = extra.get("build_system_prompt")
        if build_sys_prompt_config_fn is not None:
            system_prompt, prompt_config = build_sys_prompt_config_fn(config.domain)
        elif build_sys_prompt_fn is not None:
            res = build_sys_prompt_fn(config.domain)
            if isinstance(res, tuple):
                system_prompt, prompt_config = res
            else:
                system_prompt = res
                prompt_config = {}
        else:
            system_prompt, prompt_config = dyn["get_prompt_with_config"](
                "generate", fallback=_GENERATE_FALLBACK, variables={"domain": config.domain}
            )
        max_tokens = (
            min(int(prompt_config["max_tokens"]), legacy_max_tokens)
            if "max_tokens" in prompt_config
            else legacy_max_tokens
        )
        shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))
        response_policy_mode = "shadow" if shadow_mode else "disabled"

    return _PromptConfig(
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        prompt_name=prompt_name,
        prompt_config=prompt_config,
        response_policy_mode=response_policy_mode,
    )


def _format_generation_context(
    docs: list[dict[str, Any]],
    *,
    needs_coverage: bool,
    sources_enabled: bool,
    extra: dict[str, Any],
) -> str:
    """Format retrieved documents into the context string for the LLM prompt."""
    format_context = extra.get("format_context") or _format_context
    format_params = inspect.signature(format_context).parameters
    effective_max_context_docs = (
        len(docs) if needs_coverage else extra.get("max_context_docs", _MAX_CONTEXT_DOCS)
    )
    if "sources_enabled" in format_params:
        return format_context(  # type: ignore[call-arg]
            docs,
            effective_max_context_docs,
            sources_enabled=sources_enabled,
        )
    return format_context(docs, effective_max_context_docs)


def _build_prompt_and_messages(
    *,
    config: Any,
    needs_coverage: bool,
    sources_enabled: bool,
    docs: list[dict[str, Any]],
    style_info: Any,
    raw_history: list[Any],
    effective_query: str,
    context: str,
    dyn: dict[str, Any],
    extra: dict[str, Any],
) -> _PromptAndMessages:
    """Select prompt config, build system prompt with citation, and construct LLM messages."""
    style_enabled = bool(getattr(config, "response_style_enabled", False))
    shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))
    use_style = style_enabled and not shadow_mode

    pc = _select_prompt_config(
        config=config,
        needs_coverage=needs_coverage,
        use_style=use_style,
        style_info=style_info,
        dyn=dyn,
        extra=extra,
    )

    effective_temperature: float = pc.prompt_config.get("temperature", config.llm_temperature)
    ensure_history_instruction = (
        extra.get("ensure_history_instruction") or _ensure_history_instruction
    )
    system_prompt = ensure_history_instruction(pc.system_prompt)

    if sources_enabled and docs:
        citation_instruction = extra.get("citation_instruction", _CITATION_INSTRUCTION)
        separator = "\n" if system_prompt.endswith("\n") else "\n\n"
        system_prompt = f"{system_prompt}{separator}{citation_instruction}"

    llm_messages = _build_llm_messages(
        system_prompt=system_prompt,
        raw_history=raw_history,
        effective_query=effective_query,
        context=context,
        extra=extra,
    )

    return _PromptAndMessages(
        effective_temperature=effective_temperature,
        llm_messages=llm_messages,
        max_tokens=pc.max_tokens,
        prompt_name=pc.prompt_name,
        response_policy_mode=pc.response_policy_mode,
    )
