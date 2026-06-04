"""Core application module exports."""

from .assistant import (
    AssistantError,
    AssistantResult,
    CoreDependencies,
    CrmAction,
    UserContext,
    run_assistant_request,
)


def __getattr__(name: str) -> object:
    """Load legacy pipeline exports lazily to keep assistant imports lightweight."""

    if name == "RAGPipeline":
        from .pipeline import RAGPipeline

        return RAGPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AssistantError",
    "AssistantResult",
    "CoreDependencies",
    "CrmAction",
    "RAGPipeline",
    "UserContext",
    "run_assistant_request",
]
