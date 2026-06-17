"""Core application module exports."""

from .contracts import (
    AssistantError,
    AssistantRequest,
    AssistantResult,
    CacheProvider,
    CoreDependencies,
    EmbeddingProvider,
    LLMProvider,
    QdrantClientProtocol,
    RerankerProvider,
    SparseEmbeddingProvider,
    TelemetryLogger,
    UserContext,
)


def __getattr__(name: str) -> object:
    """Load runtime-bearing exports lazily to keep core contracts import-safe."""

    if name == "AssistantApp":
        from .app import AssistantApp

        return AssistantApp
    if name == "DependencyBuilder":
        from .app import DependencyBuilder

        return DependencyBuilder
    if name == "run_assistant_request":
        from .assistant import run_assistant_request

        return run_assistant_request
    if name == "RAGPipeline":
        from .pipeline import RAGPipeline

        return RAGPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AssistantApp",
    "AssistantError",
    "AssistantRequest",
    "AssistantResult",
    "CacheProvider",
    "CoreDependencies",
    "DependencyBuilder",
    "EmbeddingProvider",
    "LLMProvider",
    "QdrantClientProtocol",
    "RAGPipeline",
    "RerankerProvider",
    "SparseEmbeddingProvider",
    "TelemetryLogger",
    "UserContext",
    "run_assistant_request",
]
