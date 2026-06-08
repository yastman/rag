"""Runtime generation exports."""

from .contracts import GenerationCallable, GenerationRequest, GenerationResult
from .service import generate_answer

__all__ = ["GenerationCallable", "GenerationRequest", "GenerationResult", "generate_answer"]
