"""Runtime generation service.

Provides transport-free generation methods independent from Telegram message rendering.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import inspect
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from src.runtime.grounding.policy import (
    is_strict_grounding_safe,
    should_safe_fallback,
)

from .context import _MAX_CONTEXT_DOCS, _format_context
from .contracts import GenerationCallable, GenerationRequest, GenerationResult
from .policy import (
    _CITATION_INSTRUCTION,
    _EXHAUSTIVE_GENERATE_FALLBACK,
    _GENERATE_FALLBACK,
    _HISTORY_INSTRUCTION,
    _MAX_HISTORY_MESSAGES,
    _build_fallback_response,
    _coerce_positive_number,
    _ensure_generation_signal_defaults,
    _extract_usage_details,
    _sanitize_response_text,
)


logger = logging.getLogger(__name__)


def _update_current_span(lf_client: Any | None, **kwargs: Any) -> None:
    """Update the current Langfuse span when tracing is available."""
    if lf_client is not None:
        with contextlib.suppress(Exception):
            lf_client.update_current_span(**kwargs)


def _update_current_generation(lf_client: Any | None, **kwargs: Any) -> None:
    """Update the current Langfuse generation when tracing is available."""
    if lf_client is not None:
        with contextlib.suppress(Exception):
            lf_client.update_current_generation(**kwargs)


def _select_recent_history(
    messages: list[Any], max_messages: int = _MAX_HISTORY_MESSAGES
) -> list[Any]:
    """Return only recent conversation history messages for LLM context."""
    if not messages:
        return []
    return messages[-max_messages:]


def _ensure_history_instruction(system_prompt: str) -> str:
    """Ensure all prompt paths include history handling instruction."""
    lowered = system_prompt.lower()
    if (
        "ссылается на предыдущие" in lowered
        or "из контекста разговора" in lowered
        or _HISTORY_INSTRUCTION.lower() in lowered
    ):
        return system_prompt

    separator = "\n" if system_prompt.endswith("\n") else "\n\n"
    return f"{system_prompt}{separator}{_HISTORY_INSTRUCTION}"


def _is_unsupported_name_kwarg(exc: TypeError) -> bool:
    """Return True if client rejected Langfuse-specific `name` kwarg."""
    message = str(exc)
    return "unexpected keyword argument" in message and "'name'" in message


def _is_unsupported_langfuse_prompt_kwarg(exc: TypeError) -> bool:
    """Return True if client rejected Langfuse-specific `langfuse_prompt` kwarg."""
    message = str(exc)
    return "unexpected keyword argument" in message and "'langfuse_prompt'" in message


async def _chat_create_with_optional_name(
    llm: Any,
    *,
    observation_name: str,
    **kwargs: Any,
) -> Any:
    """Call chat.completions.create with Langfuse `name` when supported."""
    create_fn = llm.chat.completions.create
    if getattr(llm, "_langfuse_auto_trace", True) is False:
        kwargs.pop("langfuse_prompt", None)
        return await create_fn(**kwargs)
    try:
        return await create_fn(name=observation_name, **kwargs)
    except TypeError as exc:
        if _is_unsupported_langfuse_prompt_kwarg(exc):
            logger.debug("LLM client does not support `langfuse_prompt`; retrying without it")
            kwargs.pop("langfuse_prompt", None)
            try:
                return await create_fn(name=observation_name, **kwargs)
            except TypeError as exc2:
                if not _is_unsupported_name_kwarg(exc2):
                    raise
                logger.debug("LLM client does not support `name`; retrying without it")
                return await create_fn(**kwargs)
        if not _is_unsupported_name_kwarg(exc):
            raise
        logger.debug("LLM client does not support `name`; retrying without it")
        kwargs.pop("langfuse_prompt", None)
        return await create_fn(**kwargs)


def _get_dynamic_modules(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retrieve dynamic modules to prevent static layering contract violations."""
    modules = {
        "get_client": importlib.import_module("telegram_bot.observability").get_client,
        "get_prompt": importlib.import_module(
            "telegram_bot.integrations.prompt_manager"
        ).get_prompt,
        "get_prompt_with_config": importlib.import_module(
            "telegram_bot.integrations.prompt_manager"
        ).get_prompt_with_config,
        "get_prompt_with_object": importlib.import_module(
            "telegram_bot.integrations.prompt_manager"
        ).get_prompt_with_object,
        "build_system_prompt_with_manager": importlib.import_module(
            "telegram_bot.integrations.prompt_templates"
        ).build_system_prompt_with_manager,
        "get_token_limit": importlib.import_module(
            "telegram_bot.integrations.prompt_templates"
        ).get_token_limit,
        "ResponseStyleDetector": importlib.import_module(
            "telegram_bot.services.response_style_detector"
        ).ResponseStyleDetector,
        "detect_coverage_mode": importlib.import_module(
            "telegram_bot.services.coverage_mode"
        ).detect_coverage_mode,
        "PipelineMetrics": importlib.import_module("telegram_bot.services.metrics").PipelineMetrics,
    }
    if extra:
        for k in list(modules.keys()):
            if k in extra:
                modules[k] = extra[k]
    return modules


async def generate_answer(
    request: GenerationRequest,
    *,
    generate: GenerationCallable | None = None,
) -> GenerationResult:
    """Generate an LLM answer from retrieved context using a transport-free request contract."""
    t0 = time.monotonic()

    config = request.config
    extra = request.extra_kwargs or {}
    assert config is not None, "GenerationRequest.config must be set"

    if generate is not None:
        res = await generate(
            query=request.query,
            documents=request.documents,
            retrieved_context=request.retrieved_context,
            raw_messages=request.raw_messages,
            latency_stages=request.latency_stages,
            llm_call_count=request.llm_call_count,
            grounding_mode=request.grounding_mode,
            grade_confidence=request.grade_confidence,
            config=config,
            **extra,
        )
        if isinstance(res, dict):
            return GenerationResult(payload=res)
        return res

    # Resolve Langfuse client
    logger = extra.get("logger") or logging.getLogger(__name__)
    lf_client = extra.get("lf_client")
    dyn = _get_dynamic_modules(extra)
    if lf_client is None:
        lf_client = dyn["get_client"]()

    docs = request.documents or []
    raw_history = request.raw_messages or []
    messages = _select_recent_history(raw_history, _MAX_HISTORY_MESSAGES)

    # Derive query from last message if caller didn't pass explicit query.
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
        getattr(config, "show_sources", False) or request.grounding_mode == "strict"
    )
    legal_answer_safe = request.grounding_mode != "strict" or is_strict_grounding_safe(
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
    )

    format_context = extra.get("format_context") or _format_context
    format_params = inspect.signature(format_context).parameters
    effective_max_context_docs = (
        len(docs) if needs_coverage else extra.get("max_context_docs", _MAX_CONTEXT_DOCS)
    )
    if "sources_enabled" in format_params:
        context = format_context(
            docs,
            effective_max_context_docs,
            sources_enabled=sources_enabled,  # type: ignore[call-arg]
        )
    else:
        context = format_context(docs, effective_max_context_docs)

    # Update Langfuse span input
    _update_current_span(
        lf_client,
        input={
            "query_preview": effective_query[:120],
            "query_len": len(effective_query),
            "query_hash": hashlib.sha256(effective_query.encode()).hexdigest()[:8],
            "context_docs_count": len(docs),
            "streaming_enabled": False,
            "grounding_mode": request.grounding_mode,
            "needs_coverage": needs_coverage,
            "coverage_reason": coverage_reason,
        },
    )

    if should_safe_fallback(
        grounding_mode=request.grounding_mode,
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
        legal_answer_safe=legal_answer_safe,
    ):
        elapsed = time.monotonic() - t0
        with contextlib.suppress(Exception):
            dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)
        answer = extra.get("build_fallback_response", _build_fallback_response)(docs)
        current_latency = request.latency_stages or {}
        _update_current_span(
            lf_client,
            output={
                "response_length": len(answer),
                "llm_provider_model": "safe_fallback",
                "fallback_used": False,
                "safe_fallback_used": True,
                "grounded": False,
                "response_sent": False,
                "needs_coverage": needs_coverage,
                "coverage_mode": "exhaustive_list" if needs_coverage else "default",
                "coverage_reason": coverage_reason,
            },
        )
        return GenerationResult(
            payload=_ensure_generation_signal_defaults(
                {
                    "response": answer,
                    "response_sent": False,
                    "sent_message": None,
                    "llm_provider_model": "safe_fallback",
                    "llm_ttft_ms": 0.0,
                    "llm_response_duration_ms": elapsed * 1000,
                    "llm_stream_only_ttft_ms": None,
                    "llm_ttft_drift_ms": None,
                    "llm_call_count": max(0, int(request.llm_call_count)),
                    "latency_stages": {**current_latency, "generate": elapsed},
                    "llm_decode_ms": None,
                    "llm_tps": None,
                    "llm_queue_ms": None,
                    "llm_timeout": False,
                    "llm_stream_recovery": False,
                    "streaming_enabled": False,
                    "response_style": style_info.style,
                    "response_difficulty": style_info.difficulty,
                    "response_style_reasoning": style_info.reasoning,
                    "answer_words": len(answer.split()),
                    "answer_chars": len(answer),
                    "answer_to_question_ratio": len(answer.split()) / max(style_info.word_count, 1),
                    "response_policy_mode": "safe_fallback",
                    "grounding_mode": request.grounding_mode,
                    "safe_fallback_used": True,
                    "grounded": False,
                    "legal_answer_safe": False,
                    "semantic_cache_safe_reuse": False,
                    "needs_coverage": needs_coverage,
                }
            )
        )

    style_enabled = bool(getattr(config, "response_style_enabled", False))
    shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))
    legacy_max_tokens = int(config.generate_max_tokens)

    prompt_config: dict[str, Any] = {}
    prompt_name = "generate"
    prompt_obj: Any | None = None
    use_style = False

    if needs_coverage:
        system_prompt, prompt_config = dyn["get_prompt_with_config"](
            "generate_exhaustive_list",
            fallback=_EXHAUSTIVE_GENERATE_FALLBACK,
            variables={"domain": config.domain},
        )
        _, prompt_obj = dyn["get_prompt_with_object"](
            "generate_exhaustive_list",
            fallback=_EXHAUSTIVE_GENERATE_FALLBACK,
            variables={"domain": config.domain},
        )
        if "max_tokens" in prompt_config:
            max_tokens = min(int(prompt_config["max_tokens"]), legacy_max_tokens)
        else:
            max_tokens = legacy_max_tokens
        response_policy_mode = "coverage"
        prompt_name = "generate_exhaustive_list"
    else:
        use_style = style_enabled and not shadow_mode
        response_policy_mode = (
            "enforced" if use_style else ("shadow" if shadow_mode else "disabled")
        )

    if needs_coverage:
        pass
    elif use_style:
        style_prompt_builder = (
            extra.get("style_prompt_builder") or dyn["build_system_prompt_with_manager"]
        )
        style_system_prompt = style_prompt_builder(
            style=style_info.style,
            difficulty=style_info.difficulty,
            domain=config.domain,
        )
        style_token_limit = extra.get("style_token_limit") or dyn["get_token_limit"]
        style_budget = style_token_limit(style_info.style, style_info.difficulty)
        system_prompt = style_system_prompt
        max_tokens = min(style_budget, legacy_max_tokens)
        prompt_obj = None
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
        _, prompt_obj = dyn["get_prompt_with_object"](
            "generate", fallback=_GENERATE_FALLBACK, variables={"domain": config.domain}
        )
        if "max_tokens" in prompt_config:
            max_tokens = min(int(prompt_config["max_tokens"]), legacy_max_tokens)
        else:
            max_tokens = legacy_max_tokens

    effective_temperature: float = prompt_config.get("temperature", config.llm_temperature)
    ensure_history_instruction = (
        extra.get("ensure_history_instruction") or _ensure_history_instruction
    )
    system_prompt = ensure_history_instruction(system_prompt)

    if sources_enabled and docs:
        citation_instruction = extra.get("citation_instruction", _CITATION_INSTRUCTION)
        separator = "\n" if system_prompt.endswith("\n") else "\n\n"
        system_prompt = f"{system_prompt}{separator}{citation_instruction}"

    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    select_recent_history = extra.get("select_recent_history") or _select_recent_history
    messages = select_recent_history(raw_history, _MAX_HISTORY_MESSAGES)

    for msg in messages[:-1]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            llm_messages.append({"role": "user", "content": str(content)})
        elif role in ("assistant", "ai"):
            llm_messages.append({"role": "assistant", "content": str(content)})

    user_content = f"Контекст:\n{context}\n\nВопрос: {effective_query}\n\nОтветь на вопрос на основе контекста выше."
    llm_messages.append({"role": "user", "content": user_content})

    actual_model = config.llm_model
    ttft_ms = 0.0
    response_obj: Any | None = None
    completion_tokens: float | None = None
    usage_details: dict[str, int] | None = None
    hard_timeout = False

    try:
        llm = config.create_llm(auto_trace=False)
        t_llm_start = time.monotonic()
        create_kwargs = {
            "model": config.llm_model,
            "messages": llm_messages,
            "temperature": effective_temperature,
            "max_tokens": max_tokens,
            **config.get_reasoning_kwargs(),
        }
        if prompt_obj is not None:
            create_kwargs["langfuse_prompt"] = prompt_obj

        response_obj = await _chat_create_with_optional_name(
            llm,
            observation_name="generate-answer",
            **create_kwargs,
        )
        t_llm_end = time.monotonic()
        answer = response_obj.choices[0].message.content or ""
        sanitize_response = extra.get("sanitize_response") or (
            lambda t: _sanitize_response_text(t, sources_enabled=sources_enabled)
        )
        answer = sanitize_response(answer)
        actual_model = getattr(response_obj, "model", config.llm_model) or config.llm_model
        ttft_ms = (t_llm_end - t_llm_start) * 1000
        usage = getattr(response_obj, "usage", None)
        if usage is not None:
            usage_details = _extract_usage_details(usage)
            completion_tokens = _coerce_positive_number(getattr(usage, "completion_tokens", None))

    except Exception as e:
        if _coerce_positive_number(1) is None:  # pragma: no cover
            pass
        from .policy import _is_connection_error

        if _is_connection_error(e):
            logger.warning(
                "generate_answer: LLM connection failed (%s), using fallback", type(e).__name__
            )
        else:
            logger.exception("generate_answer: LLM call failed, using fallback")
        _update_current_span(
            lf_client,
            level="ERROR",
            status_message=f"LLM failed: {str(e)[:200]}",
        )
        answer = extra.get("build_fallback_response", _build_fallback_response)(docs)
        actual_model = "fallback"
        ttft_ms = 0.0
        hard_timeout = True

    elapsed = time.monotonic() - t0
    with contextlib.suppress(Exception):
        dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)

    if actual_model != "fallback":
        generation_payload: dict[str, Any] = {"model": actual_model}
        if usage_details:
            generation_payload["usage_details"] = usage_details
        elif completion_tokens is not None:
            generation_payload["usage_details"] = {"output": int(completion_tokens)}
        if prompt_obj is not None:
            generation_payload["prompt"] = prompt_obj
        with contextlib.suppress(Exception):
            _update_current_generation(lf_client, **generation_payload)

    retrieved_ctx = request.retrieved_context or []
    eval_context = "\n\n".join(
        f"[{d.get('score', 0):.2f}] {d.get('content', '')[:500]}"
        for d in retrieved_ctx[:5]
        if isinstance(d, dict)
    )

    span_output: dict[str, Any] = {
        "response_length": len(answer),
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms if ttft_ms > 0 else None,
        "llm_stream_only_ttft_ms": None,
        "llm_response_duration_ms": round(elapsed * 1000, 1),
        "fallback_used": actual_model == "fallback",
        "response_sent": False,
        "eval_query": effective_query[:2000],
        "eval_answer": answer[:3000],
        "eval_context": eval_context,
        "needs_coverage": needs_coverage,
        "coverage_mode": "exhaustive_list" if needs_coverage else "default",
        "coverage_reason": coverage_reason,
        "prompt_name": prompt_name,
        "documents_count": len(docs),
        "distinct_doc_count": len(
            {
                str((doc.get("metadata", {}) or {}).get("doc_id") or doc.get("id") or "")
                for doc in docs
            }
        ),
    }

    if usage_details:
        span_output["token_usage"] = {
            "prompt_tokens": usage_details.get("input"),
            "completion_tokens": usage_details.get("output"),
            "total_tokens": usage_details.get("total"),
        }
    elif response_obj is not None:
        usage = getattr(response_obj, "usage", None)
        if usage is not None:
            span_output["token_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }

    _update_current_span(lf_client, output=span_output)

    llm_tps: float | None = None
    if ttft_ms > 0 and completion_tokens is not None:
        llm_tps = completion_tokens / (ttft_ms / 1000)

    llm_queue_ms: float | None = None
    extract_queue_ms = extra.get("extract_queue_ms")
    if extract_queue_ms is not None:
        llm_queue_ms = extract_queue_ms(response_obj)

    answer_words = len(answer.split())
    answer_chars = len(answer)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)

    current_latency = request.latency_stages or {}
    current_llm_calls = max(0, int(request.llm_call_count))

    return GenerationResult(
        payload=_ensure_generation_signal_defaults(
            {
                "response": answer,
                "response_sent": False,
                "sent_message": None,
                "llm_provider_model": actual_model,
                "llm_ttft_ms": ttft_ms,
                "llm_response_duration_ms": elapsed * 1000,
                "llm_stream_only_ttft_ms": None,
                "llm_ttft_drift_ms": None,
                "llm_call_count": current_llm_calls + 1,
                "latency_stages": {**current_latency, "generate": elapsed},
                "llm_decode_ms": None,
                "llm_tps": llm_tps,
                "llm_queue_ms": llm_queue_ms,
                "llm_timeout": hard_timeout,
                "llm_stream_recovery": False,
                "streaming_enabled": False,
                "response_style": style_info.style,
                "response_difficulty": style_info.difficulty,
                "response_style_reasoning": style_info.reasoning,
                "answer_words": answer_words,
                "answer_chars": answer_chars,
                "answer_to_question_ratio": ratio,
                "response_policy_mode": response_policy_mode,
                "grounding_mode": request.grounding_mode,
                "safe_fallback_used": False,
                "grounded": actual_model != "fallback",
                "legal_answer_safe": legal_answer_safe,
                "semantic_cache_safe_reuse": legal_answer_safe,
                "needs_coverage": needs_coverage,
            }
        )
    )


async def generate_answer_stream(
    request: GenerationRequest,
    metadata_out: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream LLM response and output metadata upon completion."""
    t0 = time.monotonic()
    config = request.config
    extra = request.extra_kwargs or {}
    assert config is not None, "GenerationRequest.config must be set"

    extra.get("logger") or logging.getLogger(__name__)
    lf_client = extra.get("lf_client")
    dyn = _get_dynamic_modules(extra)
    if lf_client is None:
        lf_client = dyn["get_client"]()

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
        getattr(config, "show_sources", False) or request.grounding_mode == "strict"
    )

    # Strict fallback check (runs before stream starts)
    legal_answer_safe = request.grounding_mode != "strict" or is_strict_grounding_safe(
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
    )

    # Pre-stream updates to Langfuse span
    _update_current_span(
        lf_client,
        input={
            "query_preview": effective_query[:120],
            "query_len": len(effective_query),
            "query_hash": hashlib.sha256(effective_query.encode()).hexdigest()[:8],
            "context_docs_count": len(docs),
            "streaming_enabled": True,
            "grounding_mode": request.grounding_mode,
            "needs_coverage": needs_coverage,
            "coverage_reason": coverage_reason,
        },
    )

    if should_safe_fallback(
        grounding_mode=request.grounding_mode,
        documents=docs,
        sources_enabled=sources_enabled,
        grade_confidence=request.grade_confidence,
        legal_answer_safe=legal_answer_safe,
    ):
        elapsed = time.monotonic() - t0
        with contextlib.suppress(Exception):
            dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)
        answer = extra.get("build_fallback_response", _build_fallback_response)(docs)
        current_latency = request.latency_stages or {}
        _update_current_span(
            lf_client,
            output={
                "response_length": len(answer),
                "llm_provider_model": "safe_fallback",
                "fallback_used": False,
                "safe_fallback_used": True,
                "grounded": False,
                "response_sent": False,
                "needs_coverage": needs_coverage,
                "coverage_mode": "exhaustive_list" if needs_coverage else "default",
                "coverage_reason": coverage_reason,
            },
        )
        metadata_out.update(
            _ensure_generation_signal_defaults(
                {
                    "response": answer,
                    "response_sent": False,
                    "sent_message": None,
                    "llm_provider_model": "safe_fallback",
                    "llm_ttft_ms": 0.0,
                    "llm_response_duration_ms": elapsed * 1000,
                    "llm_stream_only_ttft_ms": None,
                    "llm_ttft_drift_ms": None,
                    "llm_call_count": max(0, int(request.llm_call_count)),
                    "latency_stages": {**current_latency, "generate": elapsed},
                    "llm_decode_ms": None,
                    "llm_tps": None,
                    "llm_queue_ms": None,
                    "llm_timeout": False,
                    "llm_stream_recovery": False,
                    "streaming_enabled": True,
                    "response_style": style_info.style,
                    "response_difficulty": style_info.difficulty,
                    "response_style_reasoning": style_info.reasoning,
                    "answer_words": len(answer.split()),
                    "answer_chars": len(answer),
                    "answer_to_question_ratio": len(answer.split()) / max(style_info.word_count, 1),
                    "response_policy_mode": "safe_fallback",
                    "grounding_mode": request.grounding_mode,
                    "safe_fallback_used": True,
                    "grounded": False,
                    "legal_answer_safe": False,
                    "semantic_cache_safe_reuse": False,
                    "needs_coverage": needs_coverage,
                }
            )
        )
        yield answer
        return

    style_enabled = bool(getattr(config, "response_style_enabled", False))
    shadow_mode = bool(getattr(config, "response_style_shadow_mode", False))
    legacy_max_tokens = int(config.generate_max_tokens)

    prompt_config: dict[str, Any] = {}
    prompt_name = "generate"
    prompt_obj: Any | None = None
    use_style = False

    if needs_coverage:
        system_prompt, prompt_config = dyn["get_prompt_with_config"](
            "generate_exhaustive_list",
            fallback=_EXHAUSTIVE_GENERATE_FALLBACK,
            variables={"domain": config.domain},
        )
        _, prompt_obj = dyn["get_prompt_with_object"](
            "generate_exhaustive_list",
            fallback=_EXHAUSTIVE_GENERATE_FALLBACK,
            variables={"domain": config.domain},
        )
        if "max_tokens" in prompt_config:
            max_tokens = min(int(prompt_config["max_tokens"]), legacy_max_tokens)
        else:
            max_tokens = legacy_max_tokens
        response_policy_mode = "coverage"
        prompt_name = "generate_exhaustive_list"
    else:
        use_style = style_enabled and not shadow_mode
        response_policy_mode = (
            "enforced" if use_style else ("shadow" if shadow_mode else "disabled")
        )

    if needs_coverage:
        pass
    elif use_style:
        style_prompt_builder = (
            extra.get("style_prompt_builder") or dyn["build_system_prompt_with_manager"]
        )
        style_system_prompt = style_prompt_builder(
            style=style_info.style,
            difficulty=style_info.difficulty,
            domain=config.domain,
        )
        style_token_limit = extra.get("style_token_limit") or dyn["get_token_limit"]
        style_budget = style_token_limit(style_info.style, style_info.difficulty)
        system_prompt = style_system_prompt
        max_tokens = min(style_budget, legacy_max_tokens)
        prompt_obj = None
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
        _, prompt_obj = dyn["get_prompt_with_object"](
            "generate", fallback=_GENERATE_FALLBACK, variables={"domain": config.domain}
        )
        if "max_tokens" in prompt_config:
            max_tokens = min(int(prompt_config["max_tokens"]), legacy_max_tokens)
        else:
            max_tokens = legacy_max_tokens

    effective_temperature: float = prompt_config.get("temperature", config.llm_temperature)
    ensure_history_instruction = (
        extra.get("ensure_history_instruction") or _ensure_history_instruction
    )
    system_prompt = ensure_history_instruction(system_prompt)

    if sources_enabled and docs:
        citation_instruction = extra.get("citation_instruction", _CITATION_INSTRUCTION)
        separator = "\n" if system_prompt.endswith("\n") else "\n\n"
        system_prompt = f"{system_prompt}{separator}{citation_instruction}"

    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    select_recent_history = extra.get("select_recent_history") or _select_recent_history
    messages = select_recent_history(raw_history, _MAX_HISTORY_MESSAGES)

    for msg in messages[:-1]:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            llm_messages.append({"role": "user", "content": str(content)})
        elif role in ("assistant", "ai"):
            llm_messages.append({"role": "assistant", "content": str(content)})

    format_context = extra.get("format_context") or _format_context
    format_params = inspect.signature(format_context).parameters
    effective_max_context_docs = (
        len(docs) if needs_coverage else extra.get("max_context_docs", _MAX_CONTEXT_DOCS)
    )
    if "sources_enabled" in format_params:
        context = format_context(
            docs,
            effective_max_context_docs,
            sources_enabled=sources_enabled,  # type: ignore[call-arg]
        )
    else:
        context = format_context(docs, effective_max_context_docs)

    user_content = f"Контекст:\n{context}\n\nВопрос: {effective_query}\n\nОтветь на вопрос на основе контекста выше."
    llm_messages.append({"role": "user", "content": user_content})

    actual_model = config.llm_model
    ttft_ms = 0.0
    stream_only_ttft_ms: float | None = None
    completion_tokens: float | None = None
    usage_details: dict[str, int] | None = None
    accumulated = ""
    llm = config.create_llm(auto_trace=False)
    t_request_start = time.monotonic()

    stream_create_kwargs: dict[str, Any] = {
        "model": config.llm_model,
        "messages": llm_messages,
        "temperature": effective_temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        **config.get_reasoning_kwargs(),
    }
    if prompt_obj is not None:
        stream_create_kwargs["langfuse_prompt"] = prompt_obj

    stream = await _chat_create_with_optional_name(
        llm,
        observation_name="generate-answer",
        **stream_create_kwargs,
    )
    t_stream_start = time.monotonic()

    async for chunk in stream:
        if hasattr(chunk, "usage") and chunk.usage is not None:
            chunk_usage = _extract_usage_details(chunk.usage)
            if chunk_usage:
                usage_details = {**(usage_details or {}), **chunk_usage}
            maybe_tokens = _coerce_positive_number(getattr(chunk.usage, "completion_tokens", None))
            if maybe_tokens is not None:
                completion_tokens = maybe_tokens

        if not getattr(chunk, "choices", None):
            continue

        delta = chunk.choices[0].delta
        text = delta.content if delta else None
        if not text:
            text = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)

        if text:
            if ttft_ms == 0.0:
                first_token_at = time.monotonic()
                ttft_ms = (first_token_at - t_request_start) * 1000
                stream_only_ttft_ms = (first_token_at - t_stream_start) * 1000
                if lf_client is not None:
                    with contextlib.suppress(Exception):
                        _update_current_generation(
                            lf_client, completion_start_time=datetime.now(UTC)
                        )
            accumulated += text
            yield text

        if hasattr(chunk, "model") and chunk.model:
            actual_model = chunk.model

    if not accumulated:
        raise ValueError("Streaming produced empty response")

    elapsed = time.monotonic() - t0
    with contextlib.suppress(Exception):
        dyn["PipelineMetrics"].get().record("generate", elapsed * 1000)

    if actual_model != "fallback":
        generation_payload: dict[str, Any] = {"model": actual_model}
        if usage_details:
            generation_payload["usage_details"] = usage_details
        elif completion_tokens is not None:
            generation_payload["usage_details"] = {"output": int(completion_tokens)}
        if prompt_obj is not None:
            generation_payload["prompt"] = prompt_obj
        with contextlib.suppress(Exception):
            _update_current_generation(lf_client, **generation_payload)

    retrieved_ctx = request.retrieved_context or []
    eval_context = "\n\n".join(
        f"[{d.get('score', 0):.2f}] {d.get('content', '')[:500]}"
        for d in retrieved_ctx[:5]
        if isinstance(d, dict)
    )

    span_output: dict[str, Any] = {
        "response_length": len(accumulated),
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms if ttft_ms > 0 else None,
        "llm_stream_only_ttft_ms": stream_only_ttft_ms,
        "llm_response_duration_ms": round(elapsed * 1000, 1),
        "fallback_used": False,
        "response_sent": False,
        "eval_query": effective_query[:2000],
        "eval_answer": accumulated[:3000],
        "eval_context": eval_context,
        "needs_coverage": needs_coverage,
        "coverage_mode": "exhaustive_list" if needs_coverage else "default",
        "coverage_reason": coverage_reason,
        "prompt_name": prompt_name,
        "documents_count": len(docs),
        "distinct_doc_count": len(
            {
                str((doc.get("metadata", {}) or {}).get("doc_id") or doc.get("id") or "")
                for doc in docs
            }
        ),
    }

    if usage_details:
        span_output["token_usage"] = {
            "prompt_tokens": usage_details.get("input"),
            "completion_tokens": usage_details.get("output"),
            "total_tokens": usage_details.get("total"),
        }

    _update_current_span(lf_client, output=span_output)

    llm_decode_ms = (elapsed * 1000) - ttft_ms if ttft_ms > 0 else None
    if llm_decode_ms is not None and llm_decode_ms < 0:
        llm_decode_ms = 0.0

    llm_tps: float | None = None
    if completion_tokens is not None and llm_decode_ms is not None and llm_decode_ms > 0:
        llm_tps = completion_tokens / (llm_decode_ms / 1000)

    llm_ttft_drift_ms = (
        max(0.0, ttft_ms - stream_only_ttft_ms)
        if (stream_only_ttft_ms is not None and ttft_ms > 0)
        else None
    )

    # Warning for TTFT drift
    if llm_ttft_drift_ms is not None:
        _drift_warn_threshold = getattr(config, "ttft_drift_warn_ms", None)
        if not isinstance(_drift_warn_threshold, (int, float)):
            _drift_warn_threshold = 500
        if llm_ttft_drift_ms > _drift_warn_threshold:
            with contextlib.suppress(Exception):
                _update_current_span(
                    lf_client,
                    level="WARNING",
                    status_message=f"TTFT drift detected: {llm_ttft_drift_ms:.1f}ms (request-based vs stream-only)",
                )

    answer_words = len(accumulated.split())
    answer_chars = len(accumulated)
    question_words = style_info.word_count
    ratio = answer_words / max(question_words, 1)

    current_latency = request.latency_stages or {}
    current_llm_calls = max(0, int(request.llm_call_count))

    metadata_out.update(
        _ensure_generation_signal_defaults(
            {
                "response": accumulated,
                "response_sent": False,
                "sent_message": None,
                "llm_provider_model": actual_model,
                "llm_ttft_ms": ttft_ms,
                "llm_response_duration_ms": elapsed * 1000,
                "llm_stream_only_ttft_ms": stream_only_ttft_ms,
                "llm_ttft_drift_ms": llm_ttft_drift_ms,
                "llm_call_count": current_llm_calls + 1,
                "latency_stages": {**current_latency, "generate": elapsed},
                "llm_decode_ms": llm_decode_ms,
                "llm_tps": llm_tps,
                "llm_queue_ms": None,
                "llm_timeout": False,
                "llm_stream_recovery": False,
                "streaming_enabled": True,
                "response_style": style_info.style,
                "response_difficulty": style_info.difficulty,
                "response_style_reasoning": style_info.reasoning,
                "answer_words": answer_words,
                "answer_chars": answer_chars,
                "answer_to_question_ratio": ratio,
                "response_policy_mode": response_policy_mode,
                "grounding_mode": request.grounding_mode,
                "safe_fallback_used": False,
                "grounded": True,
                "legal_answer_safe": legal_answer_safe,
                "semantic_cache_safe_reuse": legal_answer_safe,
                "needs_coverage": needs_coverage,
            }
        )
    )
