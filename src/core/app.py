# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

"""Assistant SDK application builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.assistant import run_assistant_request
from src.core.contracts import AssistantResult, CoreDependencies, UserContext


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


__all__ = ["AssistantApp"]
