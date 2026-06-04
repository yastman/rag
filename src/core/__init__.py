"""Core application module with main RAG pipeline."""

from .assistant import (
    AssistantError,
    AssistantResult,
    CoreDependencies,
    CrmAction,
    UserContext,
    run_assistant_request,
)
from .pipeline import RAGPipeline


__all__ = [
    "AssistantError",
    "AssistantResult",
    "CoreDependencies",
    "CrmAction",
    "RAGPipeline",
    "UserContext",
    "run_assistant_request",
]
