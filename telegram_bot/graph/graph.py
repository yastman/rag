"""Legacy graph entrypoint backed by the imperative assistant pipeline.

``build_graph`` is retained as a compatibility factory for callers that still
expect an object with ``ainvoke``.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from src.core.contracts import AssistantRequest, CoreDependencies, UserContext
from src.runtime.graph.nodes.transcribe import make_transcribe_node
from src.runtime.pipeline.assistant_pipeline import run_assistant_pipeline


logger = logging.getLogger(__name__)


class ImperativeGraph:
    """Compatibility object with the old compiled-graph ``ainvoke`` method."""

    def __init__(self, **dependencies: Any) -> None:
        self.dependencies = dependencies

    def with_config(self, **_: Any) -> ImperativeGraph:
        """Match the compiled graph fluent API used by tests/callers."""
        return self

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        """Run the imperative assistant pipeline and return graph-shaped state."""
        working = dict(state)
        if working.get("input_type") == "voice" or working.get("voice_audio") is not None:
            transcribe = make_transcribe_node(
                llm=self.dependencies.get("llm"),
                voice_language=str(self.dependencies.get("voice_language") or "ru"),
                stt_model=str(self.dependencies.get("stt_model") or "whisper"),
                show_transcription=bool(self.dependencies.get("show_transcription", True)),
                message=self.dependencies.get("message"),
            )
            working.update(await transcribe(working))

        query = _extract_query(working)
        request = AssistantRequest(
            query=query,
            collection=str(self.dependencies.get("collection", "")),
            user_context=UserContext(
                user_id=str(working.get("user_id", "")),
                session_id=str(working.get("session_id", "")),
                filters=working.get("filters"),
            ),
            request_id=str((config or {}).get("request_id") or working.get("trace_id") or ""),
        )
        deps = CoreDependencies(
            cache=cast(Any, self.dependencies.get("cache")),
            embeddings=cast(Any, self.dependencies.get("embeddings")),
            sparse_embeddings=cast(Any, self.dependencies.get("sparse_embeddings")),
            qdrant=cast(Any, self.dependencies.get("qdrant")),
            reranker=self.dependencies.get("reranker"),
            llm=self.dependencies.get("llm"),
            config=self.dependencies.get("config"),
            telemetry=self.dependencies.get("telemetry"),
        )
        result = await run_assistant_pipeline(request, dependencies=deps)

        message = self.dependencies.get("message")
        if message is not None and result.response_text:
            await message.answer(result.response_text)

        return {
            **working,
            "response": result.response_text,
            "query_type": result.request_type,
            "cache_hit": result.cache_hit,
            "documents": [],
            "sources_count": result.documents_count,
            "search_results_count": result.documents_count,
            "latency_stages": {
                **working.get("latency_stages", {}),
                "imperative": result.latency_ms / 1000,
            },
            "rerank_applied": result.rerank_applied,
            "retrieval_error_type": result.error_type,
            "input_type": working.get("input_type", "text"),
        }


def _extract_query(state: dict[str, Any]) -> str:
    if isinstance(state.get("stt_text"), str) and state["stt_text"]:
        return str(state["stt_text"])
    messages = state.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, dict):
            return str(last.get("content", ""))
        return cast(str, str(getattr(last, "content", last)))
    return str(state.get("query", ""))


def build_graph(**kwargs: Any) -> ImperativeGraph:
    """Return an imperative graph-compatible facade."""
    logger.info("Using imperative graph compatibility facade")
    return ImperativeGraph(**kwargs)


__all__ = ["ImperativeGraph", "build_graph"]
