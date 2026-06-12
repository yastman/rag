"""Public assistant core contracts.

These dataclasses define the stable boundary between transports (Telegram,
E2E, optional API) and the assistant core. They intentionally avoid importing
Telegram, FastAPI, Langfuse, OTel, or live integrations so callers can import
them in lightweight tests and tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class UserContext:
    """Minimal user/session context for core assistant request handling."""

    user_id: str = ""
    session_id: str = ""
    role: str = "client"
    filters: dict[str, Any] | None = None
    language: str = "ru"


@dataclass
class AssistantRequest:
    """Structured request object for future adapter and E2E callers."""

    query: str
    collection: str
    user_context: UserContext = field(default_factory=UserContext)
    request_id: str = ""


class CacheProvider(Protocol):
    """Semantic cache dependency used by the runtime RAG path."""

    async def check_semantic(self, *args: Any, **kwargs: Any) -> Any: ...


class EmbeddingProvider(Protocol):
    """Dense embedding dependency used by core/runtime."""

    async def aembed_query(self, text: str) -> list[float]: ...


class SparseEmbeddingProvider(Protocol):
    """Sparse embedding dependency used by core/runtime."""

    async def aembed_query(self, text: str) -> dict[str, Any]: ...


class QdrantClientProtocol(Protocol):
    """Vector search dependency used by core/runtime."""

    async def hybrid_search_rrf(self, *args: Any, **kwargs: Any) -> Any: ...


class RerankerProvider(Protocol):
    """Optional reranking dependency used by core/runtime."""

    async def rerank(self, *args: Any, **kwargs: Any) -> Any: ...


class LLMProvider(Protocol):
    """Optional language-model dependency used by core/runtime."""

    async def generate(self, *args: Any, **kwargs: Any) -> str: ...


class CrmClientProtocol(Protocol):
    """Optional CRM dependency; implementations must keep writes behind HITL."""

    async def propose_action(self, *args: Any, **kwargs: Any) -> CrmAction | None: ...


class TelemetryLogger(Protocol):
    """SDK-friendly telemetry callback surface for product events."""

    def log_event(self, event: str, **fields: Any) -> None: ...


@dataclass
class CoreDependencies:
    """Runtime collaborators required to execute the existing RAG path."""

    cache: CacheProvider
    embeddings: EmbeddingProvider
    sparse_embeddings: SparseEmbeddingProvider
    qdrant: QdrantClientProtocol
    reranker: RerankerProvider | None = None
    llm: LLMProvider | None = None
    config: object | None = None
    crm: CrmClientProtocol | None = None
    telemetry: TelemetryLogger | None = None


@dataclass
class CrmAction:
    """Intent for a proposed CRM action, awaiting explicit confirmation."""

    action_type: str
    payload: dict[str, Any]
    summary: str


@dataclass
class AssistantResult:
    """Structured response object returned by the assistant core entrypoint."""

    response_text: str
    route: str = ""
    request_type: str = ""
    retrieved_doc_ids: list[str] = field(default_factory=list)
    retrieved_sources: list[dict[str, str]] = field(default_factory=list)
    documents_count: int = 0
    latency_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    proposed_crm_action: CrmAction | None = None
    request_id: str = ""
    cache_hit: bool = False
    llm_model: str | None = None
    llm_call_count: int = 0
    rerank_applied: bool = False


class AssistantError(RuntimeError):
    """Unrecoverable error from the core assistant."""

    def __init__(self, message: str, *, error_type: str = "internal") -> None:
        super().__init__(message)
        self.error_type = error_type


__all__ = [
    "AssistantError",
    "AssistantRequest",
    "AssistantResult",
    "CacheProvider",
    "CoreDependencies",
    "CrmAction",
    "CrmClientProtocol",
    "EmbeddingProvider",
    "LLMProvider",
    "QdrantClientProtocol",
    "RerankerProvider",
    "SparseEmbeddingProvider",
    "TelemetryLogger",
    "UserContext",
]
