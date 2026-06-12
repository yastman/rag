"""Assistant SDK application builder."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.core.assistant import run_assistant_request
from src.core.contracts import AssistantResult, CoreDependencies, UserContext


DependencyBuilder = Callable[[object | None], CoreDependencies]


@dataclass(slots=True)
class AssistantApp:
    """Encapsulated assistant application for adapters and SDK callers.

    Adapters should construct this app from configuration or an explicit
    dependency builder, then call ``run_text``. That keeps concrete dependency
    wiring behind the core SDK boundary instead of spreading low-level runtime
    clients through transport code.
    """

    config: object | None = None
    dependencies: CoreDependencies | None = None

    @classmethod
    def from_dependencies(
        cls,
        dependencies: CoreDependencies,
        *,
        config: object | None = None,
    ) -> AssistantApp:
        """Build an app from an already prepared dependency bundle."""

        return cls(config=config, dependencies=dependencies)

    @classmethod
    def from_config(
        cls,
        config: object | None = None,
        *,
        dependency_builder: DependencyBuilder | None = None,
    ) -> AssistantApp:
        """Build an app from config, optionally using a dependency builder.

        When no builder is supplied the app remains in skeleton mode; this is
        useful for import-only SDK tests and documentation examples that should
        not initialize live Qdrant, LLM, embedding, or cache clients.
        """

        dependencies = dependency_builder(config) if dependency_builder is not None else None
        return cls(config=config, dependencies=dependencies)

    async def run_text(
        self,
        query: str,
        *,
        collection: str,
        user_context: UserContext | None = None,
        request_id: str | None = None,
        dependencies: CoreDependencies | None = None,
        **_: Any,
    ) -> AssistantResult:
        """Run one text request through the core assistant entrypoint."""

        return await run_assistant_request(
            query,
            collection=collection,
            user_context=user_context,
            request_id=request_id,
            dependencies=dependencies or self.dependencies,
        )


__all__ = ["AssistantApp", "DependencyBuilder"]
