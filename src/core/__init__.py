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
    DEFAULT_REQUEST_LANGUAGE,
    SUPPORTED_REQUEST_LANGUAGES,
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
    normalize_request_language,
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
    "DEFAULT_REQUEST_LANGUAGE",
    "SUPPORTED_REQUEST_LANGUAGES",
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
    "normalize_request_language",
    "run_assistant_request",
]
