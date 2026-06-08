"""Runtime generation seam.

The core generation entrypoint does not accept a Telegram ``message`` object and
does not send or stream Telegram messages. During the migration it delegates to
an injected generation callable, which lets existing adapters keep using the
legacy implementation while the runtime owns the transport-free request shape.
"""

from __future__ import annotations

from typing import Any

from .contracts import GenerationCallable, GenerationRequest, GenerationResult


async def generate_answer(
    request: GenerationRequest,
    *,
    generate: GenerationCallable,
) -> GenerationResult:
    """Generate an answer using a transport-free request contract."""

    kwargs: dict[str, Any] = {
        "query": request.query,
        "documents": request.documents,
        "grounding_mode": request.grounding_mode,
        "llm_call_count": request.llm_call_count,
    }
    if request.retrieved_context is not None:
        kwargs["retrieved_context"] = request.retrieved_context
    if request.raw_messages is not None:
        kwargs["raw_messages"] = request.raw_messages
    if request.latency_stages is not None:
        kwargs["latency_stages"] = request.latency_stages
    if request.grade_confidence is not None:
        kwargs["grade_confidence"] = request.grade_confidence
    if request.config is not None:
        kwargs["config"] = request.config
    kwargs.update(request.extra_kwargs)

    return GenerationResult(payload=await generate(**kwargs))


__all__ = ["generate_answer"]
