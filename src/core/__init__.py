"""Core application module with main RAG pipeline."""

from .assistant import (
    AssistantError,
    AssistantResult,
    CrmAction,
    UserContext,
    run_assistant_request,
)
from .pipeline import RAGPipeline


__all__ = [
    "AssistantError",
    "AssistantResult",
    "CrmAction",
    "RAGPipeline",
    "UserContext",
    "run_assistant_request",
]
