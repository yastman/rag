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

    if name == "run_assistant_request":
        from .assistant import run_assistant_request

        return run_assistant_request
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AssistantApp",
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
    "run_assistant_request",
]
