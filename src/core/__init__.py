"""Core application module exports."""

from .assistant import run_assistant_request
from .contracts import (
    AssistantError,
    AssistantRequest,
    AssistantResult,
    CoreDependencies,
    CrmAction,
    UserContext,
)


def __getattr__(name: str) -> object:
    """Load legacy pipeline exports lazily to keep assistant imports lightweight."""

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
