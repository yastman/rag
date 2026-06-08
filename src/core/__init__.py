"""Core application module exports."""

from .contracts import (
    AssistantError,
    AssistantRequest,
    AssistantResult,
    CoreDependencies,
    CrmAction,
    UserContext,
)


def __getattr__(name: str) -> object:
    """Load runtime-bearing exports lazily to keep core contracts import-safe."""

    if name == "run_assistant_request":
        from .assistant import run_assistant_request

        return run_assistant_request
    if name == "RAGPipeline":
        from .pipeline import RAGPipeline

        return RAGPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AssistantError",
    "AssistantRequest",
    "AssistantResult",
    "CoreDependencies",
    "CrmAction",
    "RAGPipeline",
    "UserContext",
    "run_assistant_request",
]
