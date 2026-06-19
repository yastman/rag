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
    """Minimal user/session context for core assistant request handling.

    Attributes:
        user_id: Unique identifier for the user initiating the request.
        session_id: Unique identifier for the current session (conversation).
        role: Role of the user (e.g., 'client').
        filters: Optional filter dictionary used to scope retrieval results.
        language: Preferred language code for responses (defaults to 'ru').
    """

    user_id: str = ""
    session_id: str = ""
    role: str = "client"
    filters: dict[str, Any] | None = None
    language: str = "ru"


@dataclass
class AssistantRequest:
    """Structured request object for adapters and E2E callers.

    Attributes:
        query: Natural language query from the user.
        collection: Name of the vector collection or domain to query.
        user_context: Contextual information about the user and session.
        request_id: Unique identifier for this request (UUID or external ID).
    """

    query: str
    collection: str
    user_context: UserContext = field(default_factory=UserContext)
    request_id: str = ""


class CacheProvider(Protocol):
    """Semantic cache dependency used by the runtime RAG path.

    Provides asynchronous check_semantic API to look up cached responses.
    """

    async def check_semantic(self, *args: Any, **kwargs: Any) -> Any: ...


class EmbeddingProvider(Protocol):
    """Dense embedding dependency used by core/runtime.

    Provides an async aembed_query method that returns dense vector embeddings.
    """

    async def aembed_query(self, text: str) -> list[float]: ...


class SparseEmbeddingProvider(Protocol):
    """Sparse embedding dependency used by core/runtime.

    Provides an async aembed_query method that returns sparse vector encodings.
    """

    async def aembed_query(self, text: str) -> dict[str, Any]: ...


class QdrantClientProtocol(Protocol):
    """Vector search dependency used by core/runtime.

    Provides a hybrid_search_rrf method for performing hybrid vector searches.
    """

    async def hybrid_search_rrf(self, *args: Any, **kwargs: Any) -> Any: ...


class RerankerProvider(Protocol):
    """Optional reranking dependency used by core/runtime.

    Provides a rerank method to rerank search results.
    """

    async def rerank(self, *args: Any, **kwargs: Any) -> Any: ...


class LLMProvider(Protocol):
    """Optional language-model dependency used by core/runtime.

    Provides a generate method to obtain a language model response.
    """

    async def generate(self, *args: Any, **kwargs: Any) -> str: ...


class TelemetryLogger(Protocol):
    """SDK-friendly telemetry callback surface for product events.

    Provides a log_event method to record product and performance metrics.
    """

    def log_event(self, event: str, **fields: Any) -> None: ...


@dataclass
class CoreDependencies:
    """Runtime collaborators required to execute the existing RAG path.

    Attributes:
        cache: Semantic cache provider used for storing and retrieving prior responses.
        embeddings: Dense embedding provider used to compute embeddings for queries.
        sparse_embeddings: Sparse embedding provider used to compute sparse embeddings.
        qdrant: Vector search client implementing the hybrid search protocol.
        reranker: Optional reranker provider for reranking search results.
        llm: Optional language model provider used to generate final responses.
        config: Optional configuration object shared across runtime components.
        telemetry: Optional telemetry logger for capturing product events.
    """

    cache: CacheProvider
    embeddings: EmbeddingProvider
    sparse_embeddings: SparseEmbeddingProvider
    qdrant: QdrantClientProtocol
    reranker: RerankerProvider | None = None
    llm: LLMProvider | None = None
    config: object | None = None
    telemetry: TelemetryLogger | None = None


@dataclass
class AssistantResult:
    """Structured response object returned by the assistant core entrypoint.

    Attributes:
        response_text: Final answer or message returned to the user.
        route: Name of the internal route or decision path taken.
        request_type: High-level category of the request (e.g., 'general', 'FAQ').
        retrieved_doc_ids: List of document identifiers retrieved from storage.
        retrieved_sources: List of source metadata dicts for the retrieved documents.
        documents_count: Total number of documents retrieved.
        latency_ms: Total pipeline latency in milliseconds.
        error_type: Optional error type string if an error occurred.
        error_message: Optional human-readable error message.
        request_id: Identifier of the originating request (echoes AssistantRequest.request_id).
        cache_hit: Indicates whether the response came from the semantic cache.
        llm_model: Name of the language model used to generate the response, if any.
        llm_call_count: Number of LLM calls made during the request.
        rerank_applied: Whether reranking was applied to the search results.
    """

    response_text: str
    route: str = ""
    request_type: str = ""
    retrieved_doc_ids: list[str] = field(default_factory=list)
    retrieved_sources: list[dict[str, str]] = field(default_factory=list)
    documents_count: int = 0
    latency_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    request_id: str = ""
    cache_hit: bool = False
    llm_model: str | None = None
    llm_call_count: int = 0
    rerank_applied: bool = False


class AssistantError(RuntimeError):
    """Unrecoverable error from the core assistant.

    Wraps an error message with a type for categorising internal failures.

    Args:
        message: Description of the error encountered.
        error_type: Short code describing the category of error (defaults to 'internal').
    """

    def __init__(self, message: str, *, error_type: str = "internal") -> None:
        super().__init__(message)
        self.error_type = error_type


__all__ = [
    "AssistantError",
    "AssistantRequest",
    "AssistantResult",
    "CacheProvider",
    "CoreDependencies",
    "EmbeddingProvider",
    "LLMProvider",
    "QdrantClientProtocol",
    "RerankerProvider",
    "SparseEmbeddingProvider",
    "TelemetryLogger",
    "UserContext",
]
