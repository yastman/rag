"""Runtime assistant pipeline exports."""


def __getattr__(name: str) -> object:
    """Load runtime pipeline exports lazily to avoid package import cycles."""

    if name == "rag_pipeline":
        from .rag import rag_pipeline

        return rag_pipeline
    if name == "run_assistant_pipeline":
        from .assistant_pipeline import run_assistant_pipeline

        return run_assistant_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["rag_pipeline", "run_assistant_pipeline"]
