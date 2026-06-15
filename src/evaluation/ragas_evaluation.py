#!/usr/bin/env python3
"""Disabled RAGAS evaluation entrypoint.

RAGAS was removed from the project dependency surfaces while resolving the
no-patch Dependabot alerts tracked by #2043. Keep this module as a small,
importable compatibility shim for old make targets and imports, but do not
pretend the RAGAS runner is active or supported.
"""

from __future__ import annotations

from typing import NoReturn


RAGAS_UNAVAILABLE_MESSAGE = (
    "RAGAS evaluation is disabled: ragas is not declared in pyproject.toml "
    "and is absent from uv.lock. See issue #2043 before restoring this "
    "dependency surface."
)


class RAGASEvaluationUnavailable(RuntimeError):
    """Raised when callers attempt to run the removed RAGAS evaluation lane."""


def require_ragas_evaluation() -> NoReturn:
    """Fail with a clear message instead of importing an undeclared dependency."""
    raise RAGASEvaluationUnavailable(RAGAS_UNAVAILABLE_MESSAGE)


async def run_ragas_evaluation() -> NoReturn:
    """Compatibility async entrypoint for old callers."""
    require_ragas_evaluation()


def main() -> NoReturn:
    """CLI entrypoint used by historical Makefile targets."""
    require_ragas_evaluation()


if __name__ == "__main__":
    main()
