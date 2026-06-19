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
