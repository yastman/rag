"""Runtime generation exports."""

from .contracts import GenerationCallable, GenerationRequest, GenerationResult
from .service import generate_answer, generate_answer_stream


__all__ = [
    "GenerationCallable",
    "GenerationRequest",
    "GenerationResult",
    "generate_answer",
    "generate_answer_stream",
]
